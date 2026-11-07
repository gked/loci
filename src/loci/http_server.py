"""
src/loci/http_server.py
HTTP REST API for the Loci vault — the backend the React frontend reads from.
It mounts /api/* only; the frontend is served separately (see README).

Run with:
    uv run uvicorn loci.http_server:app --reload --port 8765
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import subprocess
import sys
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from loci.tools.vault_init import (
    HOW_TO_CONFIGURE,
    NOT_CONFIGURED_MESSAGE,
    config_path,
    load_config,
    migrate_legacy_config,
)
from loci.tools import nx_graph as graph
from loci.tools import vault_history
from loci.tools.type_registry import get_registry
from loci.tools.frontmatter import split_frontmatter
from loci import api as vault_api

log = logging.getLogger(__name__)

_VAULT_ROOT: Path | None = None

# Migrate at import — once per process, and before the CORSMiddleware below
# reads the config. Doing it inside _read_config_file() put a file copy and
# rename on the per-request auth path, where a config that went missing between
# requests would have made an ordinary GET rewrite files on disk. Logged from
# lifespan() instead of here, because uvicorn configures logging after import.
_MIGRATION_NOTICE = migrate_legacy_config()

DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:4173"]

def _resolve_vault_root() -> Path:
    config = load_config()
    if not config:
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    return Path(config["vault_root"]).expanduser()


def _startup_error() -> str | None:
    """
    Why this process should not start, or None if it can.

    lifespan() only logs a warning when the vault cannot be resolved, so without
    this an unconfigured install prints "Application startup complete" and then
    500s on every endpoint — the one command a new user types looks like it
    worked. `make run` gates on scripts/run_preflight.py for the same reason;
    the console script had no equivalent. Kept separate from main() so it is
    reachable from a test.
    """
    try:
        root = _resolve_vault_root()
    except RuntimeError as exc:
        return str(exc)
    except KeyError:
        return f"{config_path()} has no vault_root — {HOW_TO_CONFIGURE}"
    if not root.is_dir():
        return f"vault directory does not exist: {root}"
    return None


def _vault_root() -> Path:
    if _VAULT_ROOT is not None:
        return _VAULT_ROOT
    return _resolve_vault_root()


# ---------------------------------------------------------------------------
# Local-request authorization
#
# /api/open-local hands a path to the operating system's handler, so it must
# only ever be reachable from this app's own frontend. Two independent checks
# guard it:
#
#   1. Origin allowlist — browsers set Origin themselves and page scripts
#      cannot forge it, so this rejects requests made by any other site the
#      user happens to have open. CORSMiddleware alone does NOT cover this: a
#      POST with no custom headers is a "simple" request, so the browser sends
#      it and only hides the response.
#   2. Shared token in a custom header — authenticates non-browser callers, and
#      because custom headers force a CORS preflight it also gets the browser
#      to enforce the allowlist before the request is ever sent.
#
# Origin has to be present. It used to be optional, falling back to the token
# alone, which meant any local process that had scraped the token — GET / hands
# it out in a meta tag so the packaged page can read it — reached this endpoint
# with a bare curl. Requiring the header does not make forging it impossible
# for a non-browser caller, but it stops the endpoint being something a stray
# script reaches without meaning to.
#
# The allowlist alone is not enough either. The bundled UI is served by this
# very process, so its page origin is whatever host and port uvicorn bound —
# 127.0.0.1:8765 by default, an ephemeral port under the e2e suite — which no
# static list can know. A request whose Origin names this server's own
# authority is therefore same-origin by definition and allowed; the configured
# list covers the cross-origin case, the vite dev and preview servers.
# ---------------------------------------------------------------------------

def _read_config_file() -> dict:
    """
    Read config.yml directly.

    load_config() short-circuits to {"vault_root": ...} when LOCI_VAULT_ROOT is
    set, which would hide api_token/allowed_origins, so auth settings are read
    straight from the file instead. The legacy-config migration load_config()
    would have run happens once at import; this is a pure read.
    """
    path = config_path()
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Could not read %s: %s", path, exc)
        return {}


def _load_or_create_token() -> str:
    """
    Resolve the API token, generating and persisting one on first run.

    Order: LOCI_API_TOKEN env var, then config.yml's api_token, then a freshly
    generated token written back to config.yml. When config.yml does not exist
    the token is kept in memory for the process lifetime.
    """
    env_token = os.environ.get("LOCI_API_TOKEN")
    if env_token:
        return env_token

    config = _read_config_file()
    token = config.get("api_token")
    if token:
        return str(token)

    token = secrets.token_urlsafe(32)
    path = config_path()
    if path.exists():
        config["api_token"] = token
        try:
            with open(path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
            log.info("Generated a new API token and saved it to %s", path)
        except OSError as exc:
            log.warning("Could not persist API token to %s: %s", path, exc)
    return token


def _allowed_origins() -> list[str]:
    configured = _read_config_file().get("allowed_origins")
    if isinstance(configured, list) and configured:
        return [str(o).rstrip("/") for o in configured]
    return list(DEFAULT_ALLOWED_ORIGINS)


_API_TOKEN: str | None = None


def _api_token() -> str:
    global _API_TOKEN
    if _API_TOKEN is None:
        _API_TOKEN = _load_or_create_token()
    return _API_TOKEN


# ---------------------------------------------------------------------------
# Host allowlist — the defence against DNS rebinding
#
# The Origin and token checks above guard only the two mutating routes, and the
# read routes have no check at all: they rely on CORS to keep a foreign page
# from *reading* a response. DNS rebinding defeats that. The attacker's domain
# is first resolved to their server, then re-pointed at 127.0.0.1; the browser
# now counts this API as the page's own site, so CORS no longer applies, and
# Origin and Host both name the attacker's domain, so `_is_same_origin` agrees.
# GET / even hands the page the token.
#
# What the attacker cannot change is the Host header: it carries their domain
# name. Every request is therefore refused unless its Host names this machine.
# The port is not compared — the attacker's page uses the same port.
#
# Known limit: a UI reached through a reverse proxy or under a custom hostname
# sends that name as Host and is refused until the name is added to
# `allowed_hosts` in config.yml. Likewise `--host` on a LAN address needs that
# address listed. That is the price of refusing by default. The list is read
# once, so editing it needs a restart.
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def _host_name(host: str) -> str:
    """The hostname part of a Host header value: lower-case, port removed.

    An IPv6 literal keeps its brackets, so `[::1]:8765` becomes `[::1]`. One
    trailing dot is dropped: `localhost.` names the same host as `localhost`.
    """
    host = host.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    return host.split(":", 1)[0].removesuffix(".")


_ALLOWED_HOSTS: frozenset[str] | None = None


def _allowed_hosts() -> frozenset[str]:
    """Loopback names plus anything listed under `allowed_hosts` in config.yml.

    Read once per process, like the token: it is checked on every request.
    """
    global _ALLOWED_HOSTS
    if _ALLOWED_HOSTS is None:
        configured = _read_config_file().get("allowed_hosts")
        extra = [str(h) for h in configured] if isinstance(configured, list) else []
        for entry in extra:
            if "://" in entry or "/" in entry:
                log.warning(
                    "Ignoring allowed_hosts entry %r: write a bare hostname, "
                    "without a scheme or a path.",
                    entry,
                )
        good = [h for h in extra if "/" not in h]
        _ALLOWED_HOSTS = frozenset(_host_name(h) for h in (*DEFAULT_ALLOWED_HOSTS, *good))
    return _ALLOWED_HOSTS


def _first_host_header(scope) -> str:
    """The first Host header, the one Starlette and `Header(host)` also read."""
    for name, value in scope["headers"]:
        if name == b"host":
            return value.decode("latin-1")
    return ""


_REFUSED_BODY = (
    "Host not allowed. If you reach Loci under another name, "
    "add it to allowed_hosts in config.yml, then restart Loci."
)


class HostAllowlistMiddleware:
    """Refuse any HTTP or WebSocket request whose Host does not name this machine."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            raw = _first_host_header(scope)
            if _host_name(raw) not in _allowed_hosts():
                log.warning("Refused a request with Host %r", raw)
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                response = PlainTextResponse(_REFUSED_BODY, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _bind_note(host: str) -> str | None:
    """A startup warning when `--host` is not a name the Host check accepts."""
    if _host_name(host) in _allowed_hosts():
        return None
    if host in ("0.0.0.0", "::"):
        return (
            f"listening on every interface ({host}). Browsers refuse requests "
            "unless the name in the address bar is listed under allowed_hosts "
            "in config.yml."
        )
    return (
        f"--host {host} is not in allowed_hosts, so every request will be "
        "refused. Add it to allowed_hosts in config.yml."
    )


def _is_same_origin(origin: str, host: str | None) -> bool:
    """True when Origin names the authority this request was sent to.

    Compared on netloc rather than the whole origin so a proxy terminating TLS
    in front of this process still matches: the browser reports https://, the
    Host header carries no scheme.
    """
    return bool(host) and urlparse(origin).netloc == host


def _authorize_local_request(
    origin: str | None, token: str | None, host: str | None = None
) -> None:
    """Raise 403 unless the caller is this app's own frontend."""
    if origin is None:
        raise HTTPException(status_code=403, detail="Missing Origin header")
    if not _is_same_origin(origin, host) and origin.rstrip("/") not in _allowed_origins():
        raise HTTPException(
            status_code=403, detail="Cross-origin requests are not allowed"
        )
    if not token or not secrets.compare_digest(token, _api_token()):
        raise HTTPException(status_code=403, detail="Missing or invalid API token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _VAULT_ROOT
    # Here and not in main(): `make dev` starts uvicorn on `app` directly.
    vault_history.set_source("ui")
    if _MIGRATION_NOTICE:
        log.warning(_MIGRATION_NOTICE)
    try:
        _VAULT_ROOT = _resolve_vault_root()
        graph.get(_VAULT_ROOT)
    except Exception as e:
        log.warning("Graph pre-warm failed: %s", e)
    # Resolve up front so the token exists before the first request, and so a
    # frontend served from somewhere other than the vite dev server has a value
    # to paste in.
    log.info("API token: %s", _api_token())
    log.info("Allowed origins: %s", ", ".join(_allowed_origins()))
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
# Added last so it is outermost: a refused Host never reaches CORS or a route.
app.add_middleware(HostAllowlistMiddleware)


def _parse_file(raw: str) -> dict:
    """
    Parse api.get() output into {frontmatter: dict, body: str, asset: dict | None}.

    api.get() returns a markdown string with YAML frontmatter. When the node has
    has_asset: true, asset info is appended in one of two formats:
      - Text asset: second --- block followed by file content
      - Binary/large asset: plain key: value lines appended to body
    """
    result: dict = {"frontmatter": {}, "body": "", "asset": None}
    if not raw.startswith("---"):
        result["body"] = raw
        return result

    fm_text, remainder = split_frontmatter(raw)
    if fm_text is None:
        return result

    try:
        result["frontmatter"] = yaml.safe_load(fm_text) or {}
    except Exception:
        pass

    # Text asset case: embedded second --- block with asset info + content
    m = re.search(
        r'\n\n---\nasset_path: (.+)\nasset_mime_type: (.+)\nasset_size_bytes: (\d+)\n---\n\n([\s\S]*)$',
        remainder,
    )
    if m:
        result["body"] = remainder[: m.start()].strip()
        result["asset"] = {
            "path": m.group(1).strip(),
            "mime_type": m.group(2).strip(),
            "size_bytes": int(m.group(3)),
            "content": m.group(4),
        }
        return result

    # Binary/large asset case: plain key: value lines appended after body
    m2 = re.search(
        r'\n\nasset_path: (.+)\nasset_mime_type: (.+)\nasset_size_bytes: (\d+)$',
        remainder,
    )
    if m2:
        result["body"] = remainder[: m2.start()].strip()
        result["asset"] = {
            "path": m2.group(1).strip(),
            "mime_type": m2.group(2).strip(),
            "size_bytes": int(m2.group(3)),
            "content": None,
        }
        return result

    result["body"] = remainder.strip()
    return result


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _local_path(raw: str) -> Path:
    """
    Convert an absolute path, a ~-relative path, or a local file URI to a
    filesystem path.

    `raw` arrives already percent-decoded by Starlette, so only the file:// URI
    branch decodes again — decoding a plain path a second time would corrupt
    any filename containing a literal '%'.
    """
    if raw.lower().startswith("file://"):
        parsed = urlparse(raw)
        if parsed.netloc not in ("", "localhost"):
            raise HTTPException(status_code=400, detail="Remote file URIs are not supported")
        path_text = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:[\\/]", path_text):
            path_text = path_text[1:]
    else:
        path_text = raw
        # A bare Windows path like C:\Users\me\note.md parses as scheme "c",
        # so drive letters are matched before the scheme check rejects it.
        if not _WINDOWS_DRIVE_RE.match(path_text) and urlparse(path_text).scheme:
            raise HTTPException(status_code=400, detail="Only local file paths can be opened")

    # Absoluteness is decided on the text as given. Expanding "~" first would
    # make every ~-relative path look absolute and defeat the check, so "~/" is
    # accepted as its own explicit form instead.
    if path_text.startswith("~"):
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            raise HTTPException(
                status_code=400, detail="Could not resolve the home directory in that path"
            )
        return path

    path = Path(path_text)
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail="File path must be absolute")
    return path


def _launch_system_handler(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


@app.post("/api/open-local")
def open_local_path(
    path: str = Query(...),
    origin: str | None = Header(None),
    x_loci_token: str | None = Header(None),
    host: str | None = Header(None),
):
    """Open a local file or directory with the operating system's handler."""
    _authorize_local_request(origin, x_loci_token, host)
    local_path = _local_path(path)
    if not local_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {local_path}")
    try:
        _launch_system_handler(local_path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open path: {exc}") from exc
    return {"opened": str(local_path)}


# ---------------------------------------------------------------------------
# Endpoints — /api/nodes/recent must be registered before /api/nodes/{uid}
# ---------------------------------------------------------------------------

def _history_status() -> dict:
    """History is a convenience: a failure reading its status must not make the
    whole vault look unhealthy."""
    try:
        return vault_api.history_status()
    except Exception as e:
        return {"state": "unknown", "detail": str(e)}


@app.get("/api/health")
def health():
    # `version` is the single source of truth for what the app calls itself:
    # vault_api.app_version() reads it from the installed package metadata, under
    # the distribution name `loci-vault` (not the import name `loci`). The UI reads
    # it from here rather than carrying its own literal, so there is one number
    # to bump and no way for the two to disagree.
    try:
        vr = _vault_root()
        g = graph.get(vr)
        return {
            "status": "ok",
            "version": vault_api.app_version(),
            "vault_root": str(vr),
            "node_count": g.number_of_nodes(),
            "history": _history_status(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "version": vault_api.app_version(),
            "vault_root": "",
            "node_count": 0,
            "history": {"state": "unknown", "detail": ""},
        }


@app.get("/api/history/last")
def history_last():
    """The change an undo would undo: {undoable, subject, commit, files} or
    {undoable: false, reason}. Read-only."""
    return vault_api.last_change()


@app.post("/api/undo")
def undo_last(
    origin: str | None = Header(None),
    x_loci_token: str | None = Header(None),
    host: str | None = Header(None),
    commit: str | None = Query(None),
):
    """Undo the newest vault change. Writes, so it takes the same origin and
    token check as /api/open-local. `commit` is the hash /api/history/last
    showed, required: when a newer change has landed since, nothing is undone (409)."""
    _authorize_local_request(origin, x_loci_token, host)
    if not commit:
        raise HTTPException(status_code=422, detail="commit is required: pass the hash /api/history/last showed.")
    try:
        return vault_api.undo_last_change(commit)
    except vault_history.HistoryError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (OSError, ValueError) as e:
        log.warning("undo failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Undo failed: {e}") from e


@app.get("/api/nodes/recent")
def nodes_recent(
    days: int = Query(30),
    limit: int = Query(20),
    state: str = Query("active"),
):
    vr = _vault_root()
    graph.get(vr)
    return graph.recent(days=days, limit=limit, state=state)


@app.get("/api/nodes")
def nodes_list(
    node_type: str = Query(None, alias="type"),
    tag: str = Query(None),
    subtype: str = Query(None),
    state: str = Query("active"),
):
    vr = _vault_root()
    g = graph.get(vr)
    state_filter = None if state == "all" else state
    results = graph.find(node_type=node_type, tag=tag, subtype=subtype, state=state_filter)
    augmented = []
    for item in results:
        uid = item["uid"]
        attrs = g.nodes.get(uid, {})
        augmented.append({
            **item,
            "tags": attrs.get("tags", []),
            "domains": attrs.get("domains", []),
            "summary": attrs.get("summary", ""),
            "updated_at": attrs.get("updated_at", ""),
        })
    return augmented


@app.get("/api/types")
def types_list():
    """The type vocabulary, as the vault's registry has it: canonical types in
    ontology order, then any user-defined ones. A user-defined type carries the
    canonical type it `extends`; canonical ones carry null. The UI's top bar
    shows the canonical types, and its left rail nests subtypes and user-defined
    types under them, all driven from here rather than from a list in the bundle, so a type
    added to the ontology (or by the user) shows up without a frontend change.
    The registry reloads when its files change on disk, so a type defined
    through `loci-mcp` reaches this process on the next request.
    Colours stay in the bundle — they are a design decision, not vocabulary."""
    registry = get_registry(_vault_root())
    result = []
    for td in registry.types():
        subtypes: list[str] = []
        for f in td.required_fields + td.optional_fields:
            if f.name == "subtype" and f.values:
                subtypes = list(f.values)
        result.append({"name": td.name, "extends": td.extends, "subtypes": subtypes})
    return result


@app.get("/api/nodes/{uid}/neighbors")
def node_neighbors(uid: str):
    vr = _vault_root()
    g = graph.get(vr)
    if not g.has_node(uid):
        raise HTTPException(status_code=404, detail=f"Node {uid!r} not found")
    return graph.neighbors(uid)


@app.get("/api/nodes/{uid}")
def node_get(uid: str):
    vr = _vault_root()
    graph.get(vr)
    try:
        raw = vault_api.get(uid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {uid!r} not found")
    parsed = _parse_file(raw)
    nbrs = graph.neighbors(uid)
    response: dict = {
        "uid": uid,
        "frontmatter": parsed["frontmatter"],
        "body": parsed["body"],
        "neighbors": nbrs,
    }
    if parsed["asset"]:
        response["asset"] = parsed["asset"]
    return response


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    state: str = Query("active"),
):
    vr = _vault_root()
    graph.get(vr)
    return graph.search(query=q, state=state)


@app.get("/api/graph")
def graph_data():
    vr = _vault_root()
    g = graph.get(vr)
    nodes = [
        {
            "uid": uid,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "tags": attrs.get("tags", []),
            "domains": attrs.get("domains", []),
            "summary": attrs.get("summary", ""),
            "status": attrs.get("status", ""),
            "state": attrs.get("state", "active"),
        }
        for uid, attrs in g.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, "rel_type": data.get("rel_type", "")}
        for u, v, data in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


# `loci` serves by default; a leading word out of this set means something else
# entirely. Kept as a plain prefix check rather than argparse subparsers:
# subparsers would have to redeclare every flag the subcommand owns, and
# argparse.REMAINDER silently drops leading options, which is exactly the shape
# `loci skills --yes` has.
SUBCOMMANDS = frozenset({"skills", "register"})


def split_command(argv: list[str]) -> tuple[str | None, list[str]]:
    """Peel a subcommand off the front of argv, leaving the rest untouched."""
    if argv and argv[0] in SUBCOMMANDS:
        return argv[0], argv[1:]
    return None, argv


# ---------------------------------------------------------------------------
# The frontend
#
# A checkout serves the UI with vite (`make dev`) or `vite preview` over
# app/dist (`make run`), and this process handled /api only. An installed wheel
# has neither: no app/ directory, no Node. So the release build compiles the
# bundle into src/loci/static/ and this serves it, which is what makes `loci`
# on its own a whole product rather than a backend.
#
# The token is injected into index.html here rather than baked in at build
# time. vite bakes VITE_LOCI_TOKEN from the config of whatever machine ran the
# build — on CI that is empty, and if it were not, the wheel would ship someone
# else's token. The server knows its own, and it is the one serving the page.
# ---------------------------------------------------------------------------

# Overridable so a deployment can serve a bundle from outside the package, and
# so the e2e suite can point at the one `vite build` just produced.
STATIC_DIR_ENV = "LOCI_STATIC_DIR"


def _static_dir() -> Path | None:
    """The directory holding the built frontend, or None if there isn't one.

    Resolved per request rather than at import: the env override has to be
    settable by a test that has already imported this module.
    """
    override = os.environ.get(STATIC_DIR_ENV)
    root = Path(override).expanduser() if override else Path(__file__).parent / "static"
    return root if (root / "index.html").is_file() else None


def _render_index(index: Path) -> str:
    """index.html with this server's API token in a meta tag.

    Read per request. The file is a few hundred bytes and the token can be
    generated after the first read, so caching it would save nothing and could
    serve a stale one.
    """
    html = index.read_text(encoding="utf-8")
    meta = f'<meta name="loci-token" content="{escape(_api_token(), quote=True)}">'
    if "</head>" in html:
        return html.replace("</head>", f"    {meta}\n  </head>", 1)
    return meta + html


# Declared last so every /api route is matched first — FastAPI resolves in
# declaration order, and this pattern matches everything.
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve the built frontend, falling back to index.html for app routes."""
    # An unmatched /api path is a missing endpoint, not a page. Returning the
    # app shell there would hand fetch() a 200 full of HTML to choke on.
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    static = _static_dir()
    if static is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No frontend bundle in this install. Build one with `make wheel`, "
                "or run the UI separately with `make dev` / `make run`."
            ),
        )

    # A real file — JS, CSS, the favicon. resolve() then the containment check
    # is what stops ../ in the URL reaching outside the bundle.
    root = static.resolve()
    candidate = (root / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(root):
        return FileResponse(candidate)

    return HTMLResponse(_render_index(root / "index.html"))


def build_cli():
    """The argument parser for `loci` with no subcommand — i.e. serving."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="loci",
        description="Serve the Loci API.",
        epilog="Subcommands: skills — install or update the Loci skills; register — add the MCP server to your agent.",
    )
    parser.add_argument("--host", default=os.environ.get("LOCI_UI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LOCI_UI_PORT", 8765)))
    return parser


def main() -> None:  # pragma: no cover
    """
    Entry point for the `loci` console script.

    Binds to loopback by default. This process reads and writes the vault with
    no authentication on most routes, so exposing it on a LAN address has to be
    a deliberate `--host` away rather than the default.
    """
    import uvicorn

    command, rest = split_command(sys.argv[1:])

    # Handled before the vault check on purpose: installing skills does not
    # need a vault, and refusing because none is configured yet would block the
    # one command a fresh install needs most.
    if command == "skills":
        from loci import skills_install

        raise SystemExit(skills_install.run(rest))

    if command == "register":
        from loci import clients

        raise SystemExit(clients.run_register(rest))

    args = build_cli().parse_args(rest)

    problem = _startup_error()
    if problem:
        print(f"loci: {problem}", file=sys.stderr)
        raise SystemExit(1)

    note = _bind_note(args.host)
    if note:
        print(f"loci: {note}", file=sys.stderr)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()

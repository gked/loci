"""
server/http_server.py
HTTP REST API for the Loci vault — serves the React frontend.

Run with:
    uv run uvicorn server.http_server:app --reload --port 8765
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Add server/ and server/tools/ to path so we can import api.py and its deps
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from vault_init import config_path, load_config, migrate_legacy_config
import nx_graph as graph
from frontmatter import split_frontmatter
import api as vault_api

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
        raise RuntimeError("Loci is not configured. Run: python tools/vault_init.py")
    return Path(config["vault_root"]).expanduser()


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
# Requests with no Origin at all (curl, tests, the MCP server) are allowed
# through the first check and fall back to the token. A browser always attaches
# Origin to a cross-origin POST, so this is not a hole a malicious page can use.
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


def _authorize_local_request(origin: str | None, token: str | None) -> None:
    """Raise 403 unless the caller is this app's own frontend."""
    if origin is not None and origin.rstrip("/") not in _allowed_origins():
        raise HTTPException(
            status_code=403, detail="Cross-origin requests are not allowed"
        )
    if not token or not secrets.compare_digest(token, _api_token()):
        raise HTTPException(status_code=403, detail="Missing or invalid API token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _VAULT_ROOT
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
):
    """Open a local file or directory with the operating system's handler."""
    _authorize_local_request(origin, x_loci_token)
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

@app.get("/api/health")
def health():
    # `version` is the single source of truth for what the app calls itself:
    # vault_api.app_version() reads it straight out of pyproject.toml. The UI reads
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
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "version": vault_api.app_version(),
            "vault_root": "",
            "node_count": 0,
        }


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
    state: str = Query("active"),
):
    vr = _vault_root()
    g = graph.get(vr)
    state_filter = None if state == "all" else state
    results = graph.find(node_type=node_type, tag=tag, state=state_filter)
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

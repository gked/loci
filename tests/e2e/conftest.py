"""
tests/e2e/conftest.py
Fixtures for the browser end-to-end suite.

Architecture — see tests/e2e/README.md for the full rationale.

    e2e_vault      builds a throwaway vault (base fixtures + overlay + fresh dates)
    api_server     uvicorn on an ephemeral port, LOCI_VAULT_ROOT -> e2e_vault
    web_server     `vite build` + `vite preview`, proxying /api -> api_server
    base_url       the origin under test
    app_page       a Playwright page already loaded and settled on base_url

All server fixtures are session-scoped: the vault is built once and the two
processes are started once for the whole run.

Set LOCI_E2E_BASE_URL to run the same specs against an already-running
deployment; the vault and both server fixtures then no-op. Most specs assert on
fixture data and are marked `fixture_bound` — see the README.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_facts  # noqa: E402  — same-directory module, see sys.path line above

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
BASE_FIXTURE_VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "vault"
REFERENCES_DIR = Path(__file__).resolve().parents[2] / "src" / "loci" / "skills" / "references"
OVERLAY_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "e2e-overlay"

STARTUP_TIMEOUT = 90  # seconds — generous; CI cold-starts uvicorn and vite
START_ATTEMPTS = 3  # fresh port per attempt; see _start_server

E2E_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    """
    Auto-apply the `e2e` marker to everything in this package so `make test-fast`
    (`-m 'not e2e'`) skips it without every spec needing its own decorator.

    This hook receives the whole session's items, so filter by path — the Python
    unit suite must not pick up the marker.

    Both sides of the comparison are resolved: E2E_DIR is already resolved, and
    `item.fspath` is not, so a checkout reached through a symlink would otherwise
    never match and `make test-fast` would silently try to run browser specs.
    """
    for item in items:
        if E2E_DIR in Path(item.fspath).resolve().parents:
            item.add_marker(pytest.mark.e2e)


# ---------------------------------------------------------------------------
# Remote mode
# ---------------------------------------------------------------------------

def _remote_base_url() -> str | None:
    """The origin to test against when running against a deployment, else None."""
    return os.environ.get("LOCI_E2E_BASE_URL") or None


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------

def _freshen_dates(vault: Path) -> None:
    """
    Rewrite created_at/updated_at on every node to be relative to today.

    Why: nx_graph.recent() filters on `updated_at >= now - days`
    (src/loci/tools/nx_graph.py). The checked-in fixture vault carries static
    January 2026 dates, so as real time advances every node falls outside the
    30-day window and /api/nodes/recent returns an empty list — which would make
    the Recent rail section and the command palette's default list permanently
    empty.

    Nodes are sorted by **filename** (stable, filesystem-order independent) and
    stamped `now - N hours` for N = 0, 1, 2, ... so the resulting order is
    deterministic across runs and machines. Assertions on ordering are therefore
    safe, but renaming a fixture file reshuffles which node is "most recent".

    Only files that actually get stamped consume an offset — a non-node .md in
    the vault must not push every real node an hour further into the past.

    Hours rather than days: a day per node capped the fixture vault at 30 nodes
    total, and the 31st failed the assert below rather than anything real. The
    window that matters is `recent()`'s 30 days, and hourly steps keep ~700
    nodes inside it while preserving the deterministic ordering. The last day is
    deliberately unused: `recent()` recomputes `now` server-side, so a node
    stamped exactly at the cutoff drops out when a run straddles UTC midnight.
    """
    now = datetime.now(timezone.utc)
    offset = 0
    for md_file in sorted(vault.rglob("*.md"), key=lambda p: p.name):
        text = md_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        stamp = (now - timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
        offset += 1
        out = []
        in_frontmatter = False
        seen_delimiters = 0
        for line in text.splitlines(keepends=True):
            # rstrip() rather than rstrip("\n"): a CRLF checkout yields "---\r".
            if line.rstrip() == "---":
                seen_delimiters += 1
                in_frontmatter = seen_delimiters == 1
                out.append(line)
                continue
            if in_frontmatter and line.startswith(("created_at:", "updated_at:")):
                key = line.split(":", 1)[0]
                out.append(f"{key}: '{stamp}'\n")
            else:
                out.append(line)
        md_file.write_text("".join(out), encoding="utf-8")

    # Fail loudly rather than letting the tail silently fall out of `recent()`.
    # `offset` is now the node count; the oldest node carries offset - 1 hours,
    # so anything up to 29 days' worth stays strictly inside the 30-day window.
    assert offset <= 24 * 29, (
        f"{offset} nodes stamped — the oldest sits at or beyond recent()'s "
        "30-day cutoff. Widen the window or trim the fixture vault."
    )


@pytest.fixture(scope="session")
def e2e_vault(tmp_path_factory) -> Path:
    """
    Build the vault the e2e run reads from:

      <root>/vault/    base fixture nodes + overlay nodes, dates freshened
      <root>/assets/   asset files referenced by overlay nodes

    The base fixture vault is copied rather than modified — the Python unit
    suite asserts on its contents and CLAUDE.md forbids reshaping it.
    """
    if _remote_base_url():
        pytest.skip("LOCI_E2E_BASE_URL is set — local vault not used")

    root = tmp_path_factory.mktemp("e2e-loci")
    vault = root / "vault"
    shutil.copytree(BASE_FIXTURE_VAULT, vault)

    # A user-defined type needs vault/meta/ontology-user.yaml, and the registry
    # only reads it beside a vault copy of ontology.yaml (type_registry.get_registry
    # falls back to references/ — user file ignored — when that one is absent).
    # Deliberately partial: the other meta files (relation dictionary, guides) are
    # not read by anything this suite drives, and each registry falls back to
    # references/ per file, so only the ontology needs a vault copy.
    meta = vault / "meta"
    meta.mkdir()
    shutil.copy(REFERENCES_DIR / "ontology.yaml", meta / "ontology.yaml")
    shutil.copy(OVERLAY_DIR / "meta" / "ontology-user.yaml", meta / "ontology-user.yaml")

    # "e2e-*.md", not "*.md": the overlay directory's own README.md documents the
    # fixtures and must not land in the vault as a pseudo-node.
    for overlay in OVERLAY_DIR.glob("e2e-*.md"):
        shutil.copy(overlay, vault / overlay.name)

    # Asset referenced by e2e-asset-note.md. LocalResolver resolves relative
    # paths against loci_root (= vault_root.parent), so this sits beside vault/.
    # Name and content come from vault_facts so the asset spec asserts on the
    # same values this writes.
    assets = root / "assets"
    assets.mkdir()
    (assets / vault_facts.ASSET_FILENAME).write_text(
        vault_facts.ASSET_CONTENT, encoding="utf-8"
    )

    _freshen_dates(vault)
    return vault


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

class ServerExited(RuntimeError):
    """The server process died before it answered. Retryable on a fresh port."""


class ServerTimeout(RuntimeError):
    """The server stayed alive but never became ready. Not retryable."""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn(cmd: list[str], cwd: Path, env: dict, log_path: Path) -> subprocess.Popen:
    """
    Start a long-running server with its output redirected to `log_path`.

    A file rather than a PIPE on purpose: nobody reads these pipes for the whole
    session, so a PIPE deadlocks the server the moment it fills the ~64KB OS
    buffer, and every later test then times out with no explanation.

    `start_new_session=True` puts the child in its own process group so
    `_terminate` can reach its descendants — see the note there.
    """
    with log_path.open("wb") as log:
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _log_tail(log_path: Path, limit: int = 4000) -> str:
    """Best-effort tail of a server's log, for error messages."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - diagnostics only
        return "<no output captured>"
    return text[-limit:] if text.strip() else "<no output captured>"


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    """
    Signal the process group, not just the direct child.

    Servers here are started via a shell-free exec, but `vite preview` still
    forks workers, and anything invoked through a wrapper (npm, uv) would not
    forward the signal to the process actually holding the port. Killing the
    group leaves no orphan listening after the session ends.
    """
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), sig)
        else:  # pragma: no cover - non-POSIX
            proc.send_signal(sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):  # pragma: no cover - already gone
            pass


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:  # pragma: no cover - slow shutdown
        pass
    _signal_group(proc, signal.SIGKILL)
    try:  # pragma: no cover - slow shutdown
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _wait_for_http(url, proc, what, log_path, check=None) -> None:
    """
    Poll `url` until it answers, failing fast if the process dies first.

    `check` receives the response body and returns None when the server is
    genuinely ready, or a string explaining why it is not — a 200 alone is not
    always proof (see _api_health_problem).
    """
    deadline = time.time() + STARTUP_TIMEOUT
    last_err: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise ServerExited(
                f"{what} exited with code {proc.returncode} before becoming ready.\n"
                f"{_log_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                body = resp.read()
            problem = check(body) if check else None
            if problem is None:
                return
            last_err = problem
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = repr(e)
        time.sleep(0.25)
    raise ServerTimeout(
        f"{what} not ready at {url} after {STARTUP_TIMEOUT}s: {last_err}\n"
        f"{_log_tail(log_path)}"
    )


def _start_server(what, cmd_for_port, url_for_port, cwd, env, log_dir,
                  ready_path="", check=None):
    """
    Start a server on an ephemeral port, retrying on a fresh port if it dies.

    _free_port() binds, reads the port, and releases it before the server claims
    it, so another process can take it in that window — vite's --strictPort then
    exits immediately. Only ServerExited is retried; a process that stays up but
    never answers is a real failure and must not cost 3 x STARTUP_TIMEOUT.

    Returns (proc, url). The caller owns termination.
    """
    last: ServerExited | None = None
    for attempt in range(1, START_ATTEMPTS + 1):
        port = _free_port()
        log_path = log_dir / f"{what}-{attempt}.log"
        proc = _spawn(cmd_for_port(port), cwd, env, log_path)
        url = url_for_port(port)
        try:
            _wait_for_http(f"{url}{ready_path}", proc, what, log_path, check=check)
            return proc, url
        except ServerExited as e:
            _terminate(proc)
            last = e
        except BaseException:
            _terminate(proc)
            raise
    raise ServerExited(f"{what} failed to start on {START_ATTEMPTS} ports.\n{last}")


def _api_health_problem(body: bytes) -> str | None:
    """
    /api/health returns HTTP 200 with `{"status": "error"}` when the graph fails
    to build (src/loci/http_server.py:131), so a 200 does not mean the API is
    usable. Without this the run would start against a broken backend and
    surface as a pile of confusing UI assertion failures instead of the cause.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        return f"/api/health returned non-JSON: {body[:200]!r}"
    if payload.get("status") != "ok":
        return f"/api/health status={payload.get('status')!r}: {payload.get('error')}"
    if not payload.get("node_count"):
        return "/api/health reports node_count 0 — LOCI_VAULT_ROOT not honoured?"
    return None


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def server_logs(tmp_path_factory) -> Path:
    """Directory holding each server's captured stdout/stderr for this session."""
    return tmp_path_factory.mktemp("e2e-logs")


@pytest.fixture(scope="session")
def api_server(e2e_vault, server_logs) -> str:
    """Start uvicorn against the e2e vault. Yields its base URL."""
    env = {**os.environ, "LOCI_VAULT_ROOT": str(e2e_vault)}
    proc, url = _start_server(
        "api-server",
        cmd_for_port=lambda port: [
            sys.executable, "-m", "uvicorn",
            "loci.http_server:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ],
        url_for_port=lambda port: f"http://127.0.0.1:{port}",
        cwd=REPO_ROOT,
        env=env,
        log_dir=server_logs,
        ready_path="/api/health",
        check=_api_health_problem,
    )
    try:
        yield url
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def web_server(api_server, server_logs) -> str:
    """
    Build the frontend and serve it with `vite preview`, proxying /api to the
    e2e API server. Yields the origin the browser should load.

    `preview` rather than `dev` so tests exercise the production bundle and
    don't contend with HMR websockets.

    vite is invoked directly rather than through `npm run preview`: npm does not
    forward signals to the script's child, so tearing the npm process down would
    leave the real vite server alive holding its port for the rest of the day.

    Missing frontend deps fail rather than skip: this fixture is session-scoped,
    so a skip here turns the whole e2e suite into skips and pytest reports the
    run as green — silently disabling the UI-impact check CLAUDE.md relies on.
    """
    vite_bin = APP_DIR / "node_modules" / ".bin" / "vite"
    if not vite_bin.exists():
        pytest.fail(
            "app/node_modules missing — run `npm ci --prefix app` (or `make test`, "
            "which does it for you). Set LOCI_E2E_BASE_URL to test a deployment "
            "without a local build.",
            pytrace=False,
        )

    env = {**os.environ, "LOCI_API_URL": api_server}

    build = subprocess.run(
        [str(vite_bin), "build"],
        cwd=APP_DIR, env=env, capture_output=True, text=True,
    )
    if build.returncode != 0:
        raise RuntimeError(f"vite build failed:\n{build.stdout}\n{build.stderr}")

    proc, url = _start_server(
        "web-server",
        cmd_for_port=lambda port: [
            str(vite_bin), "preview", "--port", str(port), "--strictPort",
        ],
        url_for_port=lambda port: f"http://localhost:{port}",
        cwd=APP_DIR,
        env=env,
        log_dir=server_logs,
    )
    try:
        yield url
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def base_url(request) -> str:
    """
    Origin under test. LOCI_E2E_BASE_URL wins and skips process startup
    entirely, so the same specs can run against a deployed instance.
    """
    remote = _remote_base_url()
    if remote:
        return remote.rstrip("/")
    return request.getfixturevalue("web_server")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@pytest.fixture
def app_page(page, base_url):
    """
    A page loaded on the app with the initial node list already rendered.

    Most specs want this. Use the raw `page` fixture when a test needs to
    intercept requests before the first load (see test_errors.py).
    """
    page.goto(base_url)
    page.wait_for_selector("[data-testid='vault-index']")
    page.wait_for_selector("[data-testid='node-row']")
    return page

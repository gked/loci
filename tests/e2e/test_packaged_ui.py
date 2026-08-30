"""
tests/e2e/test_packaged_ui.py
The single-process app: `loci` serving the built frontend out of the package.

Every other spec in this suite drives the split setup — vite preview for the
UI, uvicorn for the API, a proxy between them. That is the developer's layout.
What an installed wheel runs is one process serving both, and none of the rest
of the suite touches it: the static route, the SPA fallback and the token meta
tag are all new surface that only exists on that path.

Rather than pull the shared fixtures around, this builds its own bundle and
starts its own server, so nothing here changes what the other specs run.
"""

import os
import subprocess
import sys

import pytest
from playwright.sync_api import expect

from conftest import APP_DIR, REPO_ROOT, _start_server, _terminate

# A known value so the meta-tag assertion has something to compare against.
# The real server generates one and writes it to config.yml.
PACKAGED_TOKEN = "e2e-packaged-token"

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def packaged_server(e2e_vault, server_logs) -> str:
    """`vite build`, then uvicorn serving that bundle from the package path."""
    vite_bin = APP_DIR / "node_modules" / ".bin" / "vite"
    if not vite_bin.exists():
        pytest.fail(
            "app/node_modules missing — run `npm ci --prefix app` (or `make test`).",
            pytrace=False,
        )

    build = subprocess.run(
        [str(vite_bin), "build"], cwd=APP_DIR, capture_output=True, text=True,
    )
    if build.returncode != 0:
        raise RuntimeError(f"vite build failed:\n{build.stdout}\n{build.stderr}")

    # LOCI_STATIC_DIR stands in for src/loci/static/, which `make wheel`
    # populates. Pointing at app/dist tests the same code path without a build
    # product landing in the source tree mid-suite.
    env = {
        **os.environ,
        "LOCI_VAULT_ROOT": str(e2e_vault),
        "LOCI_STATIC_DIR": str(APP_DIR / "dist"),
        "LOCI_API_TOKEN": PACKAGED_TOKEN,
    }

    proc, url = _start_server(
        "packaged-server",
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
    )
    try:
        yield url
    finally:
        _terminate(proc)


@pytest.fixture
def packaged_page(page, packaged_server):
    page.goto(packaged_server, wait_until="domcontentloaded")
    return page


def test_the_app_renders_from_one_process(packaged_page):
    """No vite, no proxy — the same process answers the page, its assets and
    the API calls the page makes."""
    rows = packaged_page.locator("[data-testid='node-row']")
    expect(rows.first).to_be_visible()
    expect(rows).not_to_have_count(0)


def test_no_api_error_banner(packaged_page):
    """Same-origin /api calls have to work without the vite proxy that every
    other spec relies on."""
    expect(packaged_page.locator("[data-testid='api-error']")).to_have_count(0)


def test_the_page_carries_the_servers_token(packaged_page):
    """Stamped in as index.html is served. The bundle's build-time value is
    whatever config.yml the build machine had, so this has to win."""
    meta = packaged_page.locator('meta[name="loci-token"]')
    expect(meta).to_have_attribute("content", PACKAGED_TOKEN)


def test_a_deep_link_loads_directly(packaged_page, packaged_server):
    """A client-side route is not a file on disk. Loading one cold exercises
    the fallback that returns the app shell instead of a 404 — the thing that
    breaks first when a static mount is wired up carelessly."""
    packaged_page.goto(f"{packaged_server}/node/does-not-exist", wait_until="domcontentloaded")

    expect(packaged_page.locator("#root")).to_be_attached()
    assert packaged_page.title() == "Loci"


def test_the_page_can_call_open_local(packaged_page):
    """The regression this suite exists to catch.

    /api/open-local checks Origin, and the allowlist it checks against names
    the two vite ports — not this process, which serves the page itself on an
    ephemeral port. Every local-file link in a note 403s when the same-origin
    case is not handled, and no other spec would notice: the split setup the
    rest of the suite drives comes through the proxy on an allowed origin.

    A path that does not exist, so nothing is handed to the OS handler. 404
    means the request got past authorization, which is the whole assertion.
    """
    result = packaged_page.evaluate(
        """async () => {
            const token = document
                .querySelector('meta[name="loci-token"]')
                .getAttribute("content");
            const res = await fetch(
                "/api/open-local?path=" + encodeURIComponent("/nonexistent/loci-e2e.txt"),
                { method: "POST", headers: { "X-Loci-Token": token } },
            );
            return { status: res.status, detail: (await res.json()).detail };
        }"""
    )

    assert result["status"] == 404, result
    assert "Path not found" in result["detail"]

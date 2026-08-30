"""
tests/test_static_frontend.py
Serving the built frontend out of the package.

A checkout runs the UI separately — vite in `make dev`, `vite preview` in
`make run`. An installed wheel has neither app/ nor Node, so the release build
compiles the bundle into src/loci/static/ and the API process serves it. That
is what makes `loci` a whole product rather than a backend.

Two things here are load-bearing. The API token is stamped into index.html as
it is served, because baking it in at build time would ship whatever token the
build machine had. And the catch-all route must not swallow /api — a missing
endpoint answering 200 with an HTML page is far harder to diagnose than a 404.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loci import http_server


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A stand-in for what `make wheel` compiles into src/loci/static/."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        "<!DOCTYPE html>\n<html>\n  <head>\n    <title>Loci</title>\n  </head>\n"
        "  <body><div id=\"root\"></div></body>\n</html>\n"
    )
    (static / "assets" / "index-abc123.js").write_text("console.log('app')\n")
    (static / "monogram.svg").write_text("<svg/>\n")
    monkeypatch.setenv(http_server.STATIC_DIR_ENV, str(static))
    return static


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LOCI_API_TOKEN", "test-token-123")
    monkeypatch.setattr(http_server, "_API_TOKEN", None)
    return TestClient(http_server.app)


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------

def test_root_serves_the_app_shell(bundle, client):
    response = client.get("/")

    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_index_carries_this_servers_token(bundle, client):
    """The frontend reads this meta tag for the X-Loci-Token header. Baking the
    token into the bundle instead would put the build machine's token — or, on
    CI, an empty string — into every copy of the wheel."""
    response = client.get("/")

    assert '<meta name="loci-token" content="test-token-123">' in response.text


def test_the_token_is_escaped(bundle, client, monkeypatch):
    """Tokens are generated with token_urlsafe, but one can also be hand-set in
    config.yml, and a quote in it would otherwise break out of the attribute."""
    monkeypatch.setattr(http_server, "_API_TOKEN", 'a"><script>x</script>')

    response = client.get("/")

    assert "<script>x</script>" not in response.text
    assert "&quot;" in response.text


def test_assets_are_served(bundle, client):
    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_unknown_paths_fall_back_to_the_shell(bundle, client):
    """Client-side routes — /node/<uid> and friends — are not files on disk.
    A hard refresh on one has to return the app, not a 404."""
    response = client.get("/node/abc123")

    assert response.status_code == 200
    assert '<div id="root">' in response.text


# ---------------------------------------------------------------------------
# What the catch-all must not swallow
# ---------------------------------------------------------------------------

def test_unknown_api_paths_still_404(bundle, client):
    """The route matches everything, so without an explicit exclusion a
    misspelled endpoint would answer 200 with HTML and fetch() would fail on
    the JSON parse instead of the status."""
    response = client.get("/api/no-such-endpoint")

    assert response.status_code == 404
    assert "<div id=" not in response.text


def test_real_api_routes_still_win(bundle, client):
    """Declaration order is what keeps /api ahead of the catch-all."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert "version" in response.json()


@pytest.mark.parametrize(
    "path", ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/assets/../../../etc/passwd"]
)
def test_traversal_cannot_escape_the_bundle(bundle, client, path):
    response = client.get(path)

    assert "root:" not in response.text


# ---------------------------------------------------------------------------
# No bundle — a bare `uv build`, or a checkout running the UI separately
# ---------------------------------------------------------------------------

def test_without_a_bundle_the_api_still_serves(monkeypatch, client):
    monkeypatch.setenv(http_server.STATIC_DIR_ENV, "/nonexistent/static")

    assert client.get("/api/health").status_code == 200


def test_without_a_bundle_the_root_says_what_to_do(monkeypatch, client):
    """`make dev` and `make run` serve the UI themselves, and this process has
    never carried it before. A bare 404 would read as a broken install."""
    monkeypatch.setenv(http_server.STATIC_DIR_ENV, "/nonexistent/static")

    response = client.get("/")

    assert response.status_code == 404
    assert "make wheel" in response.json()["detail"]


def test_a_directory_without_index_html_counts_as_no_bundle(tmp_path, monkeypatch, client):
    """An interrupted `cp -R` leaves the directory there and index.html not in
    it. Serving that would hand the browser a stack trace."""
    empty = tmp_path / "half-copied"
    empty.mkdir()
    monkeypatch.setenv(http_server.STATIC_DIR_ENV, str(empty))

    assert client.get("/").status_code == 404


def test_the_default_location_is_inside_the_package(monkeypatch):
    """With no override the bundle is looked for in the packaged directory —
    the only place an installed Loci could have one."""
    import loci

    monkeypatch.delenv(http_server.STATIC_DIR_ENV, raising=False)
    package_root = Path(loci.__file__).parent

    # _static_dir() returns None when absent, so check the path it builds.
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    assert http_server._static_dir().is_relative_to(package_root)

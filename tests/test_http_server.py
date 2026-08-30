"""
Tests for loci/http_server.py — pure-function coverage for _parse_file.
No server process or vault fixture required.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from loci import http_server
from loci import api as vault_api
from loci.tools import vault_init
from loci.http_server import _parse_file


class TestParseFilePlain:
    def test_no_frontmatter_returns_raw_as_body(self):
        raw = "just a plain body"
        r = _parse_file(raw)
        assert r["frontmatter"] == {}
        assert r["body"] == "just a plain body"
        assert r["asset"] is None

    def test_empty_string(self):
        r = _parse_file("")
        assert r == {"frontmatter": {}, "body": "", "asset": None}


class TestParseFileFrontmatter:
    def test_frontmatter_and_body(self):
        raw = "---\ntitle: Hello\ntype: document\n---\n\nThe body text."
        r = _parse_file(raw)
        assert r["frontmatter"] == {"title": "Hello", "type": "document"}
        assert r["body"] == "The body text."
        assert r["asset"] is None

    def test_frontmatter_only_no_body(self):
        raw = "---\ntitle: Solo\n---\n"
        r = _parse_file(raw)
        assert r["frontmatter"] == {"title": "Solo"}
        assert r["body"] == ""
        assert r["asset"] is None

    def test_malformed_yaml_gives_empty_frontmatter(self):
        raw = "---\n: bad: yaml: [\n---\n\nsome body"
        r = _parse_file(raw)
        assert r["frontmatter"] == {}
        assert r["body"] == "some body"

    def test_incomplete_separator_gives_empty(self):
        # Only one --- with no closing delimiter
        raw = "---\ntitle: Orphan"
        r = _parse_file(raw)
        assert r["frontmatter"] == {}
        assert r["body"] == ""


class TestParseFileTextAsset:
    def test_text_asset_extracted(self):
        raw = (
            "---\ntitle: Note\nhas_asset: true\n---\n\nBody line.\n\n"
            "---\nasset_path: /vault/assets/note.txt\n"
            "asset_mime_type: text/plain\nasset_size_bytes: 42\n---\n\n"
            "asset content here"
        )
        r = _parse_file(raw)
        assert r["body"] == "Body line."
        assert r["asset"] is not None
        assert r["asset"]["path"] == "/vault/assets/note.txt"
        assert r["asset"]["mime_type"] == "text/plain"
        assert r["asset"]["size_bytes"] == 42
        assert r["asset"]["content"] == "asset content here"

    def test_text_asset_with_empty_body(self):
        raw = (
            "---\ntitle: Asset only\nhas_asset: true\n---\n\n"
            "---\nasset_path: /p/f.txt\nasset_mime_type: text/plain\nasset_size_bytes: 5\n---\n\nhello"
        )
        r = _parse_file(raw)
        assert r["body"] == ""
        assert r["asset"]["content"] == "hello"


class TestParseFileBinaryAsset:
    def test_binary_asset_extracted(self):
        raw = (
            "---\ntitle: Image\nhas_asset: true\n---\n\nCaption text.\n\n"
            "asset_path: /vault/assets/photo.jpg\n"
            "asset_mime_type: image/jpeg\nasset_size_bytes: 204800"
        )
        r = _parse_file(raw)
        assert r["body"] == "Caption text."
        assert r["asset"]["path"] == "/vault/assets/photo.jpg"
        assert r["asset"]["mime_type"] == "image/jpeg"
        assert r["asset"]["size_bytes"] == 204800
        assert r["asset"]["content"] is None


TOKEN = "test-token"


@pytest.fixture
def auth(monkeypatch):
    """Pin the API token and origin allowlist so auth is deterministic."""
    monkeypatch.setattr(http_server, "_API_TOKEN", TOKEN)
    monkeypatch.setattr(
        http_server, "_allowed_origins", lambda: ["http://localhost:5173"]
    )


@pytest.fixture
def client(auth):
    from fastapi.testclient import TestClient

    return TestClient(http_server.app)


class TestLocalPath:
    """Path parsing only — see TestOpenLocalAuth for the authorization layer."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("/Users/example/My File.pdf", Path("/Users/example/My File.pdf")),
            ("file:///Users/example/My%20File.pdf", Path("/Users/example/My File.pdf")),
            ("file://localhost/Users/example/note.txt", Path("/Users/example/note.txt")),
            # Already decoded by Starlette — a literal '%' must survive intact.
            ("/Users/example/Report%20v2.pdf", Path("/Users/example/Report%20v2.pdf")),
        ],
    )
    def test_accepts_local_paths(self, raw, expected):
        assert http_server._local_path(raw) == expected

    def test_expands_home_relative_paths(self):
        assert http_server._local_path("~/notes/spec.pdf") == Path.home() / "notes/spec.pdf"

    @pytest.mark.parametrize(
        "raw",
        [
            "relative/file.txt",
            "./file.txt",
            "https://example.com/file.txt",
            "file://remote-host/share/file.txt",
        ],
    )
    def test_rejects_non_local_or_relative_paths(self, raw):
        with pytest.raises(http_server.HTTPException) as exc_info:
            http_server._local_path(raw)

        assert exc_info.value.status_code == 400

    def test_windows_drive_letter_is_not_mistaken_for_a_url_scheme(self):
        # On POSIX this still fails, but on "must be absolute" rather than on
        # the scheme check — the drive letter itself is no longer the blocker.
        if sys.platform == "win32":
            assert http_server._local_path(r"C:\Users\example\note.md").is_absolute()
            return

        with pytest.raises(http_server.HTTPException) as exc_info:
            http_server._local_path(r"C:\Users\example\note.md")

        assert exc_info.value.detail == "File path must be absolute"


class TestOpenLocalPath:
    def test_opens_an_existing_path(self, auth):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(http_server, "_launch_system_handler") as launch,
        ):
            result = http_server.open_local_path(
                "/Users/example/My File.pdf",
                origin="http://localhost:5173",
                x_loci_token=TOKEN,
            )

        assert result == {"opened": "/Users/example/My File.pdf"}
        launch.assert_called_once_with(Path("/Users/example/My File.pdf"))

    def test_rejects_missing_paths(self, auth):
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(http_server.HTTPException) as exc_info:
                http_server.open_local_path(
                    "/missing/file.txt",
                    origin="http://localhost:5173",
                    x_loci_token=TOKEN,
                )

        assert exc_info.value.status_code == 404


class TestOpenLocalAuth:
    """
    /api/open-local launches files with the OS handler, so it must not be
    reachable from any page other than this app's own frontend.
    """

    def _post(self, client, path="/tmp/f.txt", **headers):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(http_server, "_launch_system_handler") as launch,
        ):
            response = client.post(f"/api/open-local?path={path}", headers=headers)
        return response, launch

    def test_allows_the_frontend_origin_with_a_valid_token(self, client):
        response, launch = self._post(
            client, **{"Origin": "http://localhost:5173", "X-Loci-Token": TOKEN}
        )

        assert response.status_code == 200
        launch.assert_called_once()

    def test_rejects_a_cross_origin_post_even_though_cors_allows_simple_requests(
        self, client
    ):
        # A POST with no custom headers is a CORS-simple request: the browser
        # sends it and only hides the response, so the endpoint must refuse it
        # itself rather than relying on CORSMiddleware.
        response, launch = self._post(
            client, **{"Origin": "https://evil.example", "X-Loci-Token": TOKEN}
        )

        assert response.status_code == 403
        launch.assert_not_called()

    @pytest.mark.parametrize("token", [None, "", "wrong-token"])
    def test_rejects_missing_or_invalid_tokens(self, client, token):
        headers = {} if token is None else {"X-Loci-Token": token}
        response, launch = self._post(client, **headers)

        assert response.status_code == 403
        launch.assert_not_called()

    def test_rejects_a_request_with_no_origin(self, client):
        # A missing Origin used to fall through to the token alone. GET / hands
        # the token to anyone who can reach the port, so that left the endpoint
        # one `curl` away for any local process — and this endpoint launches
        # arbitrary paths with the OS handler.
        response, launch = self._post(client, **{"X-Loci-Token": TOKEN})

        assert response.status_code == 403
        assert response.json()["detail"] == "Missing Origin header"
        launch.assert_not_called()

    def test_allows_the_servers_own_origin_even_though_it_is_not_listed(self, client):
        """The packaged UI is served by this process, so its page origin is
        whatever host and port uvicorn bound — 127.0.0.1:8765 by default, an
        ephemeral port under the e2e suite. No static allowlist can name it, so
        without a same-origin check every open-local from the wheel's own UI
        403s. TestClient sends Host: testserver."""
        response, launch = self._post(
            client, **{"Origin": "http://testserver", "X-Loci-Token": TOKEN}
        )

        assert response.status_code == 200
        launch.assert_called_once()

    def test_a_cross_origin_post_is_not_saved_by_the_same_origin_check(self, client):
        """The browser sets Host to the server it is talking to, so a page on
        another origin cannot make the two agree."""
        response, launch = self._post(
            client,
            **{
                "Origin": "https://evil.example",
                "Host": "testserver",
                "X-Loci-Token": TOKEN,
            },
        )

        assert response.status_code == 403
        launch.assert_not_called()

    @pytest.mark.parametrize(
        ("origin", "host", "expected"),
        [
            ("http://127.0.0.1:8765", "127.0.0.1:8765", True),
            ("http://localhost:41235", "localhost:41235", True),
            # A proxy terminating TLS: the browser reports https, Host does not.
            ("https://loci.example", "loci.example", True),
            ("http://127.0.0.1:8765", "127.0.0.1:5173", False),
            ("http://evil.example", None, False),
        ],
    )
    def test_same_origin_is_decided_on_the_authority(self, origin, host, expected):
        assert http_server._is_same_origin(origin, host) is expected


class TestConfigReadsDoNotWriteToDisk:
    """
    _read_config_file() runs from the per-request auth dependency. The legacy
    config migration it used to call copies and renames files, so an ordinary
    GET could rewrite the user's disk whenever the user-level config happened to
    be missing. Migration belongs to startup, and happens once at import.
    """

    def test_reading_the_config_never_migrates_a_legacy_file(self, tmp_path, monkeypatch):
        legacy = tmp_path / "checkout" / "config.yml"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("vault_root: /somewhere\n", encoding="utf-8")
        monkeypatch.setattr(vault_init, "LEGACY_CONFIG_PATH", legacy)
        monkeypatch.delenv("LOCI_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        http_server._read_config_file()

        assert legacy.exists(), "a config read must not rename the legacy file"
        assert not (tmp_path / "xdg" / "loci" / "config.yml").exists()

    def test_migration_runs_once_at_import(self):
        # The notice is captured at import and logged from lifespan(), where
        # uvicorn has already configured logging.
        assert hasattr(http_server, "_MIGRATION_NOTICE")


class TestStartupPreflight:
    """
    `loci` has to refuse to start when the vault cannot be resolved.

    lifespan() swallows the failure as a log warning, so without a preflight
    uvicorn prints "Application startup complete" and every endpoint then 500s —
    the one command a new user types looks like it worked. `make run` gates on
    scripts/run_preflight.py for the same reason.
    """

    def test_no_config_is_reported_with_the_setup_command(self, monkeypatch):
        monkeypatch.setattr(http_server, "load_config", lambda: None)

        problem = http_server._startup_error()

        assert problem is not None
        assert "uv run setup.py" in problem

    def test_config_without_a_vault_root_is_reported(self, monkeypatch):
        monkeypatch.setattr(http_server, "load_config", lambda: {"api_token": "x"})

        problem = http_server._startup_error()

        assert problem is not None
        assert "vault_root" in problem

    def test_a_vault_root_that_is_not_on_disk_is_reported(self, monkeypatch, tmp_path):
        missing = tmp_path / "unmounted-drive" / "vault"
        monkeypatch.setattr(http_server, "load_config", lambda: {"vault_root": str(missing)})

        problem = http_server._startup_error()

        assert problem is not None
        assert str(missing) in problem

    def test_a_configured_vault_on_disk_starts(self, monkeypatch, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        monkeypatch.setattr(http_server, "load_config", lambda: {"vault_root": str(vault)})

        assert http_server._startup_error() is None


class TestHealthVersion:
    """
    /api/health carries the app version so the UI has one number to render.

    Before this, VaultRail hardcoded "v0.4" while pyproject.toml said 0.1.0 and
    nothing reconciled them. These tests pin the contract the rail depends on.
    """

    def test_health_reports_the_version_from_pyproject(self, client):
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["version"] == vault_api.app_version()

    def test_version_matches_pyproject_exactly(self, client):
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        declared = next(
            line.split("=")[1].strip().strip('"')
            for line in pyproject.read_text(encoding="utf-8").splitlines()
            if line.startswith("version")
        )

        assert client.get("/api/health").json()["version"] == declared

    def test_version_is_present_even_when_the_graph_fails(self, client, monkeypatch):
        # The error branch returns its own dict, so it has to carry the version
        # too — otherwise the rail loses the number whenever the vault is broken,
        # which is exactly when you want to know what you are running.
        monkeypatch.setattr(
            http_server, "_vault_root", lambda: (_ for _ in ()).throw(RuntimeError("no vault"))
        )

        payload = client.get("/api/health").json()

        assert payload["status"] == "error"
        assert payload["version"] == vault_api.app_version()


class TestPackagingConstraints:
    """
    Guards on metadata that only breaks off the developer's machine.

    A checkout resolves through uv.lock and never notices these; a fresh
    install from the wheel is where they bite.
    """

    def _pyproject(self) -> str:
        return (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")

    def test_mcp_is_pinned_below_2(self):
        # mcp 2.x renamed FastMCP to MCPServer. While the server imports
        # FastMCP, an unbounded `mcp` requirement makes every fresh install
        # resolve a version that cannot import.
        from loci import mcp_server

        source = Path(mcp_server.__file__).read_text(encoding="utf-8")
        if "mcp.server.fastmcp" not in source:
            pytest.skip("server no longer imports FastMCP — the bound can be revisited")

        assert 'mcp[cli]>=1.0,<2' in self._pyproject()

    def test_console_scripts_are_declared(self):
        # The two entry points are the whole install story; losing one turns a
        # working install into an importable library with no way to start it.
        pyproject = self._pyproject()
        assert 'loci-mcp = "loci.mcp_server:main"' in pyproject
        assert 'loci = "loci.http_server:main"' in pyproject

    def test_entry_points_are_callable(self):
        from loci import http_server, mcp_server

        assert callable(mcp_server.main)
        assert callable(http_server.main)

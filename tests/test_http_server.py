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
    # Pinned so a developer's own config.yml cannot change what the tests see.
    monkeypatch.setattr(
        http_server, "_ALLOWED_HOSTS", frozenset(http_server.DEFAULT_ALLOWED_HOSTS)
    )


@pytest.fixture
def client(auth):
    from fastapi.testclient import TestClient

    # TestClient's default Host is `testserver`, which the Host allowlist refuses.
    return TestClient(http_server.app, base_url="http://localhost")


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
        403s. The client sends Host: localhost."""
        response, launch = self._post(
            client, **{"Origin": "http://localhost", "X-Loci-Token": TOKEN}
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
                "Host": "localhost",
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

    @pytest.mark.parametrize(
        "config",
        [None, {"api_token": "x"}],
        ids=["no config file", "config without vault_root"],
    )
    def test_both_config_failures_name_the_tool_a_wheel_install_can_use(
        self, monkeypatch, config
    ):
        """
        `setup.py` ships only in a checkout, so it cannot be the only way out.

        The reader most likely to hit either failure installed the wheel and
        typed `loci` — for them `uv run setup.py` is a dead end, and
        set_vault_root is the way in. The skills say the same thing (see "Do
        not substitute a setup command for it" in loci-save/SKILL.md).
        """
        monkeypatch.setattr(http_server, "load_config", lambda: config)

        problem = http_server._startup_error()

        assert problem is not None
        assert "set_vault_root" in problem
        assert problem.index("set_vault_root") < problem.index("setup.py")

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


class TestHealthLanguage:
    """/api/health carries the configured language so the UI can open in it."""

    def test_defaults_to_english(self, client, monkeypatch):
        monkeypatch.delenv("LOCI_LANGUAGE", raising=False)
        assert client.get("/api/health").json()["language"] == "en"

    def test_reports_the_configured_language(self, client, monkeypatch):
        monkeypatch.setenv("LOCI_LANGUAGE", "ru")
        assert client.get("/api/health").json()["language"] == "ru-RU"

    def test_error_payload_carries_it_too(self, client, monkeypatch):
        monkeypatch.setenv("LOCI_LANGUAGE", "ru-RU")
        monkeypatch.setattr(
            http_server, "_vault_root", lambda: (_ for _ in ()).throw(RuntimeError("no vault"))
        )
        payload = client.get("/api/health").json()
        assert payload["status"] == "error"
        assert payload["language"] == "ru-RU"


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


class TestHostAllowlist:
    """DNS rebinding: the attacker's page ends up talking to 127.0.0.1, but its
    Host header still carries the attacker's domain."""

    @pytest.mark.parametrize(
        "host", ["localhost", "localhost:8765", "127.0.0.1:8765", "[::1]:8765", "LOCALHOST"]
    )
    def test_loopback_names_are_served(self, client, host):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200

    @pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.evil.example", ""])
    def test_any_other_host_is_refused_on_a_read_route(self, client, host):
        """Read routes have no token check, so this is the only guard on them."""
        response = client.get("/api/nodes", headers={"Host": host})

        assert response.status_code == 403
        assert "allowed_hosts" in response.text

    def test_the_token_page_is_not_handed_to_a_rebound_host(self, client):
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 403

    def test_a_rebound_post_is_refused_even_with_matching_origin_and_token(self, client):
        """Origin and Host agree under rebinding, so the same-origin check passes."""
        response = client.post(
            "/api/undo",
            headers={
                "Origin": "http://evil.example",
                "Host": "evil.example",
                "X-Loci-Token": TOKEN,
            },
        )

        assert response.status_code == 403
        assert "allowed_hosts" in response.text

    def test_a_host_listed_in_config_is_served(self, client, monkeypatch):
        monkeypatch.setattr(http_server, "_ALLOWED_HOSTS", None)
        monkeypatch.setattr(
            http_server, "_read_config_file", lambda: {"allowed_hosts": ["Loci.Lan", "10.0.0.5"]}
        )

        assert client.get("/api/health", headers={"Host": "loci.lan:8765"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "10.0.0.5"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "localhost"}).status_code == 200

    def test_the_body_says_to_restart_after_editing_the_list(self, client):
        response = client.get("/api/nodes", headers={"Host": "evil.example"})

        assert "restart" in response.text.lower()

    @staticmethod
    def _drive(scope):
        """Run the middleware once; return (messages sent, whether the app ran).

        Runs on its own thread: the browser suite leaves an event loop running
        on the main thread, and `asyncio.run` refuses to start inside one.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        sent, served = [], []

        async def app(scope, receive, send):
            served.append(True)

        async def send(message):
            sent.append(message)

        def go():
            asyncio.run(http_server.HostAllowlistMiddleware(app)(scope, None, send))

        with ThreadPoolExecutor(1) as pool:
            pool.submit(go).result()
        return sent, bool(served)

    def test_the_first_host_header_decides(self):
        """Starlette reads the first Host header, so the guard must too."""
        sent, served = self._drive(
            {"type": "http", "headers": [(b"host", b"evil.example"), (b"host", b"localhost")]}
        )
        assert not served and sent[0]["status"] == 403

        _, served = self._drive(
            {"type": "http", "headers": [(b"host", b"localhost"), (b"host", b"evil.example")]}
        )
        assert served

    def test_a_request_with_no_host_header_is_refused(self):
        sent, served = self._drive({"type": "http", "headers": []})

        assert not served and sent[0]["status"] == 403

    def test_a_websocket_with_a_foreign_host_is_closed(self):
        sent, served = self._drive(
            {"type": "websocket", "headers": [(b"host", b"evil.example")]}
        )

        assert not served
        assert sent == [{"type": "websocket.close", "code": 1008}]

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
    def test_binding_to_loopback_prints_no_note(self, host):
        assert http_server._bind_note(host) is None

    def test_binding_to_a_lan_address_names_allowed_hosts(self):
        assert "allowed_hosts" in http_server._bind_note("192.168.1.5")

    def test_binding_to_every_interface_names_allowed_hosts(self):
        assert "allowed_hosts" in http_server._bind_note("0.0.0.0")

    @pytest.mark.parametrize("host", ["localhost.", "localhost.:8765", "127.0.0.1."])
    def test_a_trailing_dot_names_the_same_host(self, client, host):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200

    def test_a_trailing_dot_in_config_matches_the_bare_name(self, client, monkeypatch):
        monkeypatch.setattr(http_server, "_ALLOWED_HOSTS", None)
        monkeypatch.setattr(http_server, "_read_config_file", lambda: {"allowed_hosts": ["loci.lan."]})

        assert client.get("/api/health", headers={"Host": "loci.lan"}).status_code == 200

    def test_an_entry_with_a_scheme_is_warned_about_and_not_matched(
        self, client, monkeypatch, caplog
    ):
        monkeypatch.setattr(http_server, "_ALLOWED_HOSTS", None)
        monkeypatch.setattr(
            http_server, "_read_config_file", lambda: {"allowed_hosts": ["http://loci.lan:8765"]}
        )

        assert client.get("/api/health", headers={"Host": "http"}).status_code == 403
        assert "http://loci.lan:8765" in caplog.text
        assert client.get("/api/health", headers={"Host": "loci.lan"}).status_code == 403

    def test_a_malformed_allowed_hosts_setting_falls_back_to_loopback(self, client, monkeypatch):
        monkeypatch.setattr(http_server, "_ALLOWED_HOSTS", None)
        monkeypatch.setattr(http_server, "_read_config_file", lambda: {"allowed_hosts": "loci.lan"})

        assert client.get("/api/health", headers={"Host": "loci.lan"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "localhost"}).status_code == 200

    @pytest.mark.parametrize(
        ("raw", "name"),
        [
            ("localhost:8765", "localhost"),
            ("Example.COM", "example.com"),
            ("[::1]:8765", "[::1]"),
            ("[::1]", "[::1]"),
            ("[::1", "[::1"),
            ("", ""),
        ],
    )
    def test_host_name_strips_the_port(self, raw, name):
        assert http_server._host_name(raw) == name


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


class TestUndoEndpoints:
    """GET /api/history/last previews an undo; POST /api/undo does it and
    takes the same origin and token check as /api/open-local."""

    HEADERS = {"Origin": "http://localhost:5173", "X-Loci-Token": TOKEN}

    @pytest.fixture(autouse=True)
    def history_on(self, monkeypatch, tmp_vault):
        monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
        monkeypatch.setattr(http_server, "_VAULT_ROOT", tmp_vault)

    def _save_and_patch(self):
        saved = vault_api.save(type="document", title="Undo Me", body="hello",
                               extra_fields={"status": "draft", "subtype": "note"})
        vault_api.patch(saved["uid"], {}, body="oops")
        return saved

    def test_last_shows_the_change_without_making_it(self, client):
        saved = self._save_and_patch()
        body = client.get("/api/history/last").json()
        assert body["undoable"] and body["subject"].startswith("Update Undo Me")
        assert "oops" in vault_api.get(saved["uid"])

    def test_undo_reverts_the_newest_change(self, client):
        saved = self._save_and_patch()
        shown = client.get("/api/history/last").json()["commit"]
        response = client.post(f"/api/undo?commit={shown}", headers=self.HEADERS)
        assert response.status_code == 200
        assert "hello" in vault_api.get(saved["uid"])

    def test_undo_without_a_commit_is_refused_and_writes_nothing(self, client):
        saved = self._save_and_patch()
        response = client.post("/api/undo", headers=self.HEADERS)
        assert response.status_code == 422
        assert "oops" in vault_api.get(saved["uid"])

    def test_undo_with_a_one_character_commit_is_a_409(self, client):
        saved = self._save_and_patch()
        shown = client.get("/api/history/last").json()["commit"]
        response = client.post(f"/api/undo?commit={shown[0]}", headers=self.HEADERS)
        assert response.status_code == 409
        assert "too short" in response.json()["detail"]
        assert "oops" in vault_api.get(saved["uid"])

    def test_undo_with_a_disk_failure_says_why(self, client, monkeypatch):
        self._save_and_patch()
        shown = client.get("/api/history/last").json()["commit"]

        def boom(*a, **k):
            raise OSError("disk is full")

        monkeypatch.setattr(vault_api, "undo_last_change", boom)
        response = client.post(f"/api/undo?commit={shown}", headers=self.HEADERS)
        assert response.status_code == 500
        assert "disk is full" in response.json()["detail"]

    def test_undo_of_a_change_that_is_no_longer_the_newest_is_a_409(self, client):
        saved = self._save_and_patch()
        shown = client.get("/api/history/last").json()["commit"]
        vault_api.patch(saved["uid"], {}, body="newer")      # lands after the user saw `shown`
        response = client.post(f"/api/undo?commit={shown}", headers=self.HEADERS)
        assert response.status_code == 409
        assert "changed since" in response.json()["detail"]
        assert "newer" in vault_api.get(saved["uid"])

    def test_undo_of_the_change_that_was_shown_goes_through(self, client):
        saved = self._save_and_patch()
        shown = client.get("/api/history/last").json()["commit"]
        response = client.post(f"/api/undo?commit={shown}", headers=self.HEADERS)
        assert response.status_code == 200
        assert "hello" in vault_api.get(saved["uid"])

    def test_undo_without_a_token_writes_nothing(self, client):
        saved = self._save_and_patch()
        response = client.post("/api/undo", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 403
        assert "oops" in vault_api.get(saved["uid"])

    def test_undo_from_another_origin_is_refused(self, client):
        saved = self._save_and_patch()
        response = client.post(
            "/api/undo", headers={"Origin": "https://evil.example", "Host": "localhost", "X-Loci-Token": TOKEN}
        )
        assert response.status_code == 403
        assert "oops" in vault_api.get(saved["uid"])

    def test_nothing_to_undo_is_a_409_with_the_reason(self, client):
        response = client.post("/api/undo?commit=abcdef0", headers=self.HEADERS)
        assert response.status_code == 409
        assert "history" in response.json()["detail"]
        assert client.get("/api/history/last").json()["undoable"] is False

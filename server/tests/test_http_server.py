"""
Tests for server/http_server.py — pure-function coverage for _parse_file.
No server process or vault fixture required.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import http_server
from http_server import _parse_file


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
                "/Users/example/My File.pdf", origin=None, x_loci_token=TOKEN
            )

        assert result == {"opened": "/Users/example/My File.pdf"}
        launch.assert_called_once_with(Path("/Users/example/My File.pdf"))

    def test_rejects_missing_paths(self, auth):
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(http_server.HTTPException) as exc_info:
                http_server.open_local_path(
                    "/missing/file.txt", origin=None, x_loci_token=TOKEN
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

    def test_allows_a_tokened_request_with_no_origin(self, client):
        # curl, tests, and the MCP server send no Origin. A browser always
        # attaches one to a cross-origin POST, so this is not a bypass.
        response, launch = self._post(client, **{"X-Loci-Token": TOKEN})

        assert response.status_code == 200
        launch.assert_called_once()

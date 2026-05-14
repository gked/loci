"""
tests/test_resolvers.py
Tests for tools/resolvers/: LocalResolver, UrlResolver, and dispatcher.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx

from resolvers.base import Resolver
from resolvers.external_resolver import ExternalResolver
from resolvers.local_resolver import LocalResolver
from resolvers.url_resolver import UrlResolver
from resolvers.dispatcher import dispatch_resolve, dispatch_enumerate, registered_schemes


# ---------------------------------------------------------------------------
# LocalResolver
# ---------------------------------------------------------------------------

@pytest.fixture
def loci_root(tmp_path):
    """Create a minimal loci root with an assets/ directory."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "abc12345.pdf").write_bytes(b"%PDF-1.4 test content")
    (assets / "abc12345.txt").write_text("hello world", encoding="utf-8")
    return tmp_path


class TestLocalResolverCapabilities:
    def test_declares_resolve_and_enumerate(self, loci_root):
        r = LocalResolver(loci_root)
        assert "resolve" in r.capabilities
        assert "enumerate" in r.capabilities


class TestLocalResolverResolve:
    def test_resolves_existing_file(self, loci_root):
        r = LocalResolver(loci_root)
        result = r.resolve({"scheme": "local", "path": "assets/abc12345.pdf"})
        assert result["path"].endswith("abc12345.pdf")
        assert result["size_bytes"] > 0
        assert result["mime_type"] == "application/pdf"
        assert "mtime" in result["metadata"]

    def test_resolves_text_file_mime(self, loci_root):
        r = LocalResolver(loci_root)
        result = r.resolve({"scheme": "local", "path": "assets/abc12345.txt"})
        assert "text/plain" in result["mime_type"]

    def test_raises_for_missing_file(self, loci_root):
        r = LocalResolver(loci_root)
        with pytest.raises(FileNotFoundError):
            r.resolve({"scheme": "local", "path": "assets/nothere.pdf"})

    def test_raises_for_missing_path_field(self, loci_root):
        r = LocalResolver(loci_root)
        with pytest.raises(ValueError, match="path"):
            r.resolve({"scheme": "local"})


class TestLocalResolverEnumerate:
    def test_enumerates_directory(self, loci_root):
        r = LocalResolver(loci_root)
        items = r.enumerate({"scheme": "local", "path": "assets"})
        names = [i["path"] for i in items]
        assert any("abc12345.pdf" in n for n in names)
        assert any("abc12345.txt" in n for n in names)

    def test_each_item_has_scheme_and_path(self, loci_root):
        r = LocalResolver(loci_root)
        items = r.enumerate({"scheme": "local", "path": "assets"})
        for item in items:
            assert item["scheme"] == "local"
            assert "path" in item
            assert "title" in item

    def test_skips_dotfiles(self, loci_root):
        (loci_root / "assets" / ".hidden").write_text("secret")
        r = LocalResolver(loci_root)
        items = r.enumerate({"scheme": "local", "path": "assets"})
        paths = [i["path"] for i in items]
        assert not any(".hidden" in p for p in paths)

    def test_raises_for_missing_directory(self, loci_root):
        r = LocalResolver(loci_root)
        with pytest.raises(FileNotFoundError):
            r.enumerate({"scheme": "local", "path": "no-such-dir"})

    def test_raises_for_file_not_directory(self, loci_root):
        r = LocalResolver(loci_root)
        with pytest.raises(NotADirectoryError):
            r.enumerate({"scheme": "local", "path": "assets/abc12345.pdf"})

    def test_raises_for_missing_path_field(self, loci_root):
        r = LocalResolver(loci_root)
        with pytest.raises(ValueError, match="path"):
            r.enumerate({"scheme": "local"})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestDispatcher:
    def test_registered_schemes_includes_local(self):
        assert "local" in registered_schemes()

    def test_dispatch_resolve_local(self, loci_root):
        result = dispatch_resolve(
            {"scheme": "local", "path": "assets/abc12345.pdf"}, loci_root
        )
        assert result["size_bytes"] > 0

    def test_dispatch_enumerate_local(self, loci_root):
        items = dispatch_enumerate({"scheme": "local", "path": "assets"}, loci_root)
        assert len(items) > 0

    def test_dispatch_resolve_unknown_scheme(self, loci_root):
        with pytest.raises(ValueError, match="No resolver registered"):
            dispatch_resolve({"scheme": "ftp", "path": "file.txt"}, loci_root)

    def test_dispatch_resolve_missing_scheme(self, loci_root):
        with pytest.raises(ValueError, match="missing 'scheme'"):
            dispatch_resolve({"path": "assets/abc12345.pdf"}, loci_root)

    def test_dispatch_enumerate_unknown_scheme(self, loci_root):
        with pytest.raises(ValueError, match="No resolver registered"):
            dispatch_enumerate({"scheme": "ftp", "path": "dir"}, loci_root)

    def test_dispatch_enumerate_missing_scheme(self, loci_root):
        with pytest.raises(ValueError, match="missing 'scheme'"):
            dispatch_enumerate({"path": "assets"}, loci_root)

    def test_all_canonical_schemes_registered(self):
        schemes = registered_schemes()
        for s in ["local", "url", "google-drive", "nextcloud", "gmail",
                  "icloud-drive", "onedrive", "dropbox", "s3", "ssh-remote"]:
            assert s in schemes, f"scheme '{s}' missing from dispatcher"

    def test_dispatch_resolve_external_scheme_returns_location_with_marker(self, loci_root):
        result = dispatch_resolve({"scheme": "google-drive", "file_id": "abc123"}, loci_root)
        assert result["file_id"] == "abc123"
        assert result["resolution"] == "external"

    def test_dispatch_enumerate_external_scheme_raises(self, loci_root):
        with pytest.raises(ValueError, match="does not support enumerate"):
            dispatch_enumerate({"scheme": "google-drive", "file_id": "folder123"}, loci_root)

    def test_dispatch_resolve_url(self, loci_root):
        mock_response = MagicMock()
        mock_response.url = "https://example.com/doc.pdf"
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = b"%PDF test"
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        with patch("resolvers.url_resolver.httpx.Client", return_value=mock_client):
            result = dispatch_resolve(
                {"scheme": "url", "url": "https://example.com/doc.pdf"}, loci_root
            )
        assert result["scheme"] == "url"
        assert result["mime_type"] == "application/pdf"
        assert result["size_bytes"] > 0

    def test_dispatch_enumerate_url_raises(self, loci_root):
        with pytest.raises(ValueError, match="does not support enumerate"):
            dispatch_enumerate({"scheme": "url", "url": "https://example.com"}, loci_root)


# ---------------------------------------------------------------------------
# ExternalResolver
# ---------------------------------------------------------------------------

_EXTERNAL_SCHEMES = [
    "google-drive", "nextcloud", "gmail", "icloud-drive",
    "onedrive", "dropbox", "s3", "ssh-remote",
]


class TestExternalResolver:
    def test_declares_only_resolve(self):
        r = ExternalResolver("google-drive")
        assert "resolve" in r.capabilities
        assert "enumerate" not in r.capabilities

    @pytest.mark.parametrize("scheme", _EXTERNAL_SCHEMES)
    def test_resolve_returns_location_plus_marker(self, scheme):
        location = {"scheme": scheme, "file_id": "xyz"}
        result = ExternalResolver(scheme).resolve(location)
        assert result["scheme"] == scheme
        assert result["file_id"] == "xyz"
        assert result["resolution"] == "external"

    @pytest.mark.parametrize("scheme", _EXTERNAL_SCHEMES)
    def test_enumerate_raises_not_implemented(self, scheme):
        with pytest.raises(NotImplementedError):
            ExternalResolver(scheme).enumerate({"scheme": scheme})


# ---------------------------------------------------------------------------
# UrlResolver
# ---------------------------------------------------------------------------

def _make_mock_response(url, content, content_type="text/html", status=200):
    mock_response = MagicMock()
    mock_response.url = url
    mock_response.status_code = status
    mock_response.headers = {"content-type": content_type}
    mock_response.content = content
    mock_response.raise_for_status = MagicMock()
    return mock_response


def _patched_client(response):
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = MagicMock(return_value=response)
    return mock_client


class TestUrlResolverCapabilities:
    def test_declares_only_resolve(self):
        r = UrlResolver()
        assert "resolve" in r.capabilities
        assert "enumerate" not in r.capabilities


class TestUrlResolverResolve:
    def test_resolves_html_page(self):
        body = b"<html><body>hello</body></html>"
        resp = _make_mock_response("https://example.com/page", body, "text/html; charset=utf-8")
        with patch("resolvers.url_resolver.httpx.Client", return_value=_patched_client(resp)):
            result = UrlResolver().resolve({"scheme": "url", "url": "https://example.com/page"})
        assert result["mime_type"] == "text/html"
        assert result["content"] == body
        assert result["size_bytes"] == len(body)
        assert result["metadata"]["status_code"] == 200

    def test_resolves_pdf(self):
        body = b"%PDF-1.4 content"
        resp = _make_mock_response("https://example.com/f.pdf", body, "application/pdf")
        with patch("resolvers.url_resolver.httpx.Client", return_value=_patched_client(resp)):
            result = UrlResolver().resolve({"scheme": "url", "url": "https://example.com/f.pdf"})
        assert result["mime_type"] == "application/pdf"

    def test_strips_charset_from_content_type(self):
        body = b"data"
        resp = _make_mock_response(
            "https://example.com/", body, "text/plain; charset=utf-8"
        )
        with patch("resolvers.url_resolver.httpx.Client", return_value=_patched_client(resp)):
            result = UrlResolver().resolve({"scheme": "url", "url": "https://example.com/"})
        assert result["mime_type"] == "text/plain"

    def test_raises_for_missing_url_field(self):
        with pytest.raises(ValueError, match="url"):
            UrlResolver().resolve({"scheme": "url"})

    def test_raises_for_non_http_scheme(self):
        with pytest.raises(ValueError, match="unsupported URL scheme"):
            UrlResolver().resolve({"scheme": "url", "url": "ftp://example.com/file"})

    def test_raises_on_http_error(self):
        resp = _make_mock_response("https://example.com/gone", b"", status=404)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        with patch("resolvers.url_resolver.httpx.Client", return_value=_patched_client(resp)):
            with pytest.raises(httpx.HTTPStatusError):
                UrlResolver().resolve({"scheme": "url", "url": "https://example.com/gone"})

    def test_enumerate_raises(self):
        with pytest.raises(NotImplementedError):
            UrlResolver().enumerate({"scheme": "url", "url": "https://example.com"})

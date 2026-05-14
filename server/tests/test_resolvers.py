"""
tests/test_resolvers.py
Tests for tools/resolvers/: LocalResolver and dispatcher.
"""

import pytest
from pathlib import Path

from resolvers.base import Resolver
from resolvers.local_resolver import LocalResolver
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
            dispatch_resolve({"scheme": "google-drive", "file_id": "abc"}, loci_root)

    def test_dispatch_resolve_missing_scheme(self, loci_root):
        with pytest.raises(ValueError, match="missing 'scheme'"):
            dispatch_resolve({"path": "assets/abc12345.pdf"}, loci_root)

    def test_dispatch_enumerate_unknown_scheme(self, loci_root):
        with pytest.raises(ValueError, match="No resolver registered"):
            dispatch_enumerate({"scheme": "s3", "bucket": "b", "key": "k"}, loci_root)

    def test_dispatch_enumerate_missing_scheme(self, loci_root):
        with pytest.raises(ValueError, match="missing 'scheme'"):
            dispatch_enumerate({"path": "assets"}, loci_root)

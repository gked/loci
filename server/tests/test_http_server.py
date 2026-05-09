"""
Tests for server/http_server.py — pure-function coverage for _parse_file.
No server process or vault fixture required.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
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

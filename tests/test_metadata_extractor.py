"""
tests/test_metadata_extractor.py
Tests for tools/metadata_extractor.py.
"""

import zipfile
import io
from pathlib import Path

import pytest

from loci.tools import metadata_extractor as me


# ---------------------------------------------------------------------------
# extract_from_filename
# ---------------------------------------------------------------------------

def test_extract_from_filename_author_title_split(tmp_path):
    path = tmp_path / "Umberto Eco - The Name of the Rose.epub"
    result = me.extract_from_filename(path)
    assert result["author"] == "Umberto Eco"
    assert result["title"] == "The Name of the Rose"


def test_extract_from_filename_no_dash_uses_stem(tmp_path):
    path = tmp_path / "just_a_title.epub"
    result = me.extract_from_filename(path)
    assert "title" in result
    assert result["title"] == "just a title"
    assert "author" not in result


def test_extract_from_filename_hyphen_in_stem(tmp_path):
    path = tmp_path / "my-document.md"
    result = me.extract_from_filename(path)
    assert "title" in result
    assert result["title"] == "my-document"  # hyphens preserved
    assert "author" not in result


def test_extract_from_filename_split_on_first_dash_only(tmp_path):
    path = tmp_path / "Author Name - Book Title - Extra.epub"
    result = me.extract_from_filename(path)
    assert result["author"] == "Author Name"
    assert result["title"] == "Book Title - Extra"


# ---------------------------------------------------------------------------
# extract_metadata — non-existent path (should not crash)
# ---------------------------------------------------------------------------

def test_extract_metadata_nonexistent_path_returns_dict(tmp_path):
    path = tmp_path / "doesnotexist.epub"
    result = me.extract_metadata(path)
    assert isinstance(result, dict)
    # Should have mime_type and format at minimum
    assert "mime_type" in result
    assert "format" in result


def test_extract_metadata_nonexistent_pdf_returns_dict(tmp_path):
    path = tmp_path / "doesnotexist.pdf"
    result = me.extract_metadata(path)
    assert isinstance(result, dict)
    assert result["mime_type"] == "application/pdf"
    assert result["format"] == "pdf"


def test_extract_metadata_unknown_extension(tmp_path):
    path = tmp_path / "somefile.xyz"
    result = me.extract_metadata(path)
    assert isinstance(result, dict)
    assert "title" in result
    assert result["format"] == "xyz"


# ---------------------------------------------------------------------------
# extract_epub_metadata — minimal valid epub
# ---------------------------------------------------------------------------

def _make_minimal_epub(tmp_path: Path, title: str, author: str, language: str = "en") -> Path:
    """Create a minimal valid epub file for testing."""
    epub_path = tmp_path / "test.epub"

    opf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:identifier id="uid">urn:isbn:1234567890</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"/>
</package>"""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", opf_content)
    epub_path.write_bytes(buf.getvalue())
    return epub_path


def test_extract_epub_metadata_happy_path(tmp_path):
    epub = _make_minimal_epub(tmp_path, "The Name of the Rose", "Umberto Eco", "it")
    result = me.extract_epub_metadata(epub)
    assert result.get("title") == "The Name of the Rose"
    assert result.get("author") == "Umberto Eco"
    assert result.get("language") == "it"
    assert result.get("identifier") == "urn:isbn:1234567890"


def test_extract_epub_metadata_invalid_file_returns_extraction_error(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not an epub")
    result = me.extract_epub_metadata(bad)
    assert "_extraction_error" in result
    assert result["_extraction_error"].startswith("epub:")


# ---------------------------------------------------------------------------
# MIME_TYPES mapping
# ---------------------------------------------------------------------------

def test_mime_types_epub():
    assert me.MIME_TYPES[".epub"] == "application/epub+zip"


def test_mime_types_pdf():
    assert me.MIME_TYPES[".pdf"] == "application/pdf"


def test_mime_types_mobi():
    assert me.MIME_TYPES[".mobi"] == "application/x-mobipocket-ebook"


# ---------------------------------------------------------------------------
# extract_metadata dispatches correctly
# ---------------------------------------------------------------------------

def test_extract_metadata_fills_from_filename_when_epub_missing(tmp_path):
    """If epub metadata extraction fails, filename fallback applies."""
    bad_epub = tmp_path / "Tolkien - The Hobbit.epub"
    bad_epub.write_bytes(b"not a real epub")
    result = me.extract_metadata(bad_epub)
    assert result["title"] == "The Hobbit"
    assert result["author"] == "Tolkien"
    assert result["format"] == "epub"
    assert result["mime_type"] == "application/epub+zip"


def test_extract_metadata_epub_metadata_takes_priority_over_filename(tmp_path):
    """epub metadata should win over filename-derived values."""
    epub = _make_minimal_epub(tmp_path, "OPF Title", "OPF Author")
    # Rename to have a different author in filename
    renamed = tmp_path / "Wrong Author - Wrong Title.epub"
    epub.rename(renamed)
    result = me.extract_metadata(renamed)
    assert result["title"] == "OPF Title"
    assert result["author"] == "OPF Author"

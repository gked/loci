"""
tests/test_inbox_scanner.py
Tests for tools/inbox_scanner.py.
"""

from pathlib import Path

import pytest

import inbox_scanner as scanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stage_root(tmp_path):
    """Create a minimal loci-stage/ structure."""
    root = tmp_path / "loci-stage"
    root.mkdir()
    (root / "files").mkdir()
    (root / "unresolved").mkdir()
    return root


# ---------------------------------------------------------------------------
# classify tests (via scan_stage)
# ---------------------------------------------------------------------------

def test_epub_in_files_dir_classifies_as_file_asset_book(stage_root):
    (stage_root / "files" / "book.epub").write_bytes(b"fake epub")
    result = scanner.scan_stage(stage_root)
    items = result["items"]
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "file"
    assert item["action"] == "ingest-asset"
    assert item["type"] == "asset"
    assert item["subtype"] == "book"
    assert item["format"] == "epub"
    assert item["path"] == "files/book.epub"


def test_mobi_in_files_dir_classifies_as_ebook(stage_root):
    (stage_root / "files" / "book.mobi").write_bytes(b"fake mobi")
    result = scanner.scan_stage(stage_root)
    assert len(result["items"]) == 1
    assert result["items"][0]["subtype"] == "book"


def test_pdf_in_files_dir_goes_to_unresolved(stage_root):
    (stage_root / "files" / "thesis.pdf").write_bytes(b"fake pdf")
    result = scanner.scan_stage(stage_root)
    assert len(result["items"]) == 0
    assert len(result["unresolved"]) == 1
    u = result["unresolved"][0]
    assert u["path"] == "files/thesis.pdf"
    assert len(u["options"]) > 0


def test_md_in_root_classifies_as_content_document(stage_root):
    (stage_root / "note.md").write_text("# My Note\n", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    items = result["items"]
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "content"
    assert item["action"] == "save-document"
    assert item["type"] == "document"
    assert item["path"] == "note.md"


def test_txt_in_root_classifies_as_content_document(stage_root):
    (stage_root / "notes.txt").write_text("plain text", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    items = result["items"]
    assert any(it["type"] == "document" for it in items)


def test_html_in_root_classifies_as_content_article(stage_root):
    (stage_root / "page.html").write_text("<html/>", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    items = result["items"]
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "content"
    assert item["action"] == "save-content"
    assert item["type"] == "article"


def test_pdf_in_flat_root_goes_to_unresolved(stage_root):
    (stage_root / "report.pdf").write_bytes(b"fake pdf")
    result = scanner.scan_stage(stage_root)
    assert len(result["unresolved"]) == 1
    assert result["unresolved"][0]["path"] == "report.pdf"


def test_inbox_plan_yaml_is_skipped(stage_root):
    (stage_root / ".inbox-plan.yaml").write_text("version: 1\n", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    assert len(result["items"]) == 0
    assert len(result["unresolved"]) == 0


def test_hidden_files_are_skipped(stage_root):
    (stage_root / ".hidden-file.md").write_text("secret", encoding="utf-8")
    (stage_root / "files" / ".hidden.epub").write_bytes(b"hidden")
    result = scanner.scan_stage(stage_root)
    assert len(result["items"]) == 0
    assert len(result["unresolved"]) == 0


def test_epub_in_root_classifies_as_file_asset_book(stage_root):
    """User dropped ebook in wrong folder — still classifies correctly."""
    (stage_root / "book.epub").write_bytes(b"fake epub")
    result = scanner.scan_stage(stage_root)
    items = result["items"]
    assert len(items) == 1
    item = items[0]
    assert item["category"] == "file"
    assert item["subtype"] == "book"


def test_unknown_extension_goes_to_unresolved(stage_root):
    (stage_root / "file.xyz").write_bytes(b"unknown")
    result = scanner.scan_stage(stage_root)
    assert len(result["unresolved"]) == 1


def test_summary_counts_are_correct(stage_root):
    (stage_root / "files" / "book1.epub").write_bytes(b"epub")
    (stage_root / "files" / "book2.epub").write_bytes(b"epub")
    (stage_root / "note.md").write_text("content", encoding="utf-8")
    (stage_root / "files" / "thesis.pdf").write_bytes(b"pdf")

    result = scanner.scan_stage(stage_root)
    summary = result["summary"]
    assert summary["total_files"] == 2
    assert summary["total_content"] == 1
    assert summary["total_unresolved"] == 1


def test_runs_estimated_calculated_correctly(stage_root):
    # Create 51 epub files to exceed one run of 50
    files_dir = stage_root / "files"
    for i in range(51):
        (files_dir / f"book{i:03d}.epub").write_bytes(b"epub")
    result = scanner.scan_stage(stage_root)
    assert result["summary"]["runs_estimated"]["files"] == 2  # ceil(51/50)


def test_items_have_sequential_ids(stage_root):
    (stage_root / "files" / "book1.epub").write_bytes(b"epub")
    (stage_root / "files" / "book2.epub").write_bytes(b"epub")
    (stage_root / "note.md").write_text("content", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    ids = [it["id"] for it in result["items"]]
    assert ids == list(range(1, len(ids) + 1))


def test_scan_empty_stage(stage_root):
    result = scanner.scan_stage(stage_root)
    assert result["items"] == []
    assert result["unresolved"] == []
    assert result["summary"]["total_files"] == 0
    assert result["summary"]["total_content"] == 0


def test_subdirs_in_root_are_skipped(stage_root):
    """Subdirectories in the flat root (other than files/ and unresolved/) are skipped."""
    subdir = stage_root / "otherdir"
    subdir.mkdir()
    (subdir / "note.md").write_text("content", encoding="utf-8")
    result = scanner.scan_stage(stage_root)
    # The file inside subdir should not appear
    paths = [it["path"] for it in result["items"]]
    assert not any("otherdir" in p for p in paths)


def test_azw3_classifies_as_ebook(stage_root):
    (stage_root / "files" / "book.azw3").write_bytes(b"azw3")
    result = scanner.scan_stage(stage_root)
    assert len(result["items"]) == 1
    assert result["items"][0]["subtype"] == "book"


def test_nested_folders_in_files_dir_are_scanned(stage_root):
    """Books in subdirectories of loci-stage/files/ are discovered recursively."""
    subdir = stage_root / "files" / "Fantasy"
    subdir.mkdir()
    (subdir / "book.epub").write_bytes(b"fake epub")
    deep = subdir / "Series"
    deep.mkdir()
    (deep / "part2.epub").write_bytes(b"fake epub")
    result = scanner.scan_stage(stage_root)
    paths = [it["path"] for it in result["items"]]
    assert "files/Fantasy/book.epub" in paths
    assert "files/Fantasy/Series/part2.epub" in paths
    assert len(result["items"]) == 2

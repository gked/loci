"""
tests/test_directory_scanner.py
Tests for tools/directory_scanner.py.
"""

import pytest
from pathlib import Path

from loci.tools.directory_scanner import scan_directory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault_node(vault_root: Path, uid: str, path: str) -> Path:
    """Write a minimal vault node with a has_asset local location."""
    content = f"""---
uid: {uid}
type: document
title: Test Node {uid}
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: local
        path: {path}
---

Body.
"""
    node_path = vault_root / f"test-node-{uid}.md"
    node_path.write_text(content, encoding="utf-8")
    return node_path


# ---------------------------------------------------------------------------
# Basic scans
# ---------------------------------------------------------------------------

def test_empty_directory(tmp_vault, tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = scan_directory(str(empty_dir), tmp_vault)
    assert result["total_files"] == 0
    assert result["unregistered"] == []
    assert result["registered"] == []


def test_nonexistent_directory(tmp_vault, tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_directory(str(tmp_path / "does-not-exist"), tmp_vault)


def test_path_is_file(tmp_vault, tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(NotADirectoryError):
        scan_directory(str(f), tmp_vault)


def test_all_unregistered(tmp_vault, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "report.pdf").write_bytes(b"%PDF")
    (d / "notes.txt").write_text("notes")

    result = scan_directory(str(d), tmp_vault)
    assert result["total_files"] == 2
    assert len(result["unregistered"]) == 2
    assert result["registered"] == []

    filenames = {e["filename"] for e in result["unregistered"]}
    assert filenames == {"report.pdf", "notes.txt"}


def test_all_registered(tmp_vault, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    pdf = d / "report.pdf"
    pdf.write_bytes(b"%PDF")

    _make_vault_node(tmp_vault, "aa112233", str(pdf))

    result = scan_directory(str(d), tmp_vault)
    assert result["total_files"] == 1
    assert result["unregistered"] == []
    assert len(result["registered"]) == 1
    assert result["registered"][0]["node_uid"] == "aa112233"


def test_mixed_registered_and_unregistered(tmp_vault, tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    registered_file = d / "registered.pdf"
    registered_file.write_bytes(b"%PDF")
    (d / "unregistered.txt").write_text("new")

    _make_vault_node(tmp_vault, "bb223344", str(registered_file))

    result = scan_directory(str(d), tmp_vault)
    assert result["total_files"] == 2
    assert len(result["registered"]) == 1
    assert len(result["unregistered"]) == 1
    assert result["registered"][0]["filename"] == "registered.pdf"
    assert result["unregistered"][0]["filename"] == "unregistered.txt"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def test_format_from_extension(tmp_vault, tmp_path):
    d = tmp_path / "formats"
    d.mkdir()
    (d / "doc.PDF").write_bytes(b"%PDF")   # uppercase extension
    (d / "sheet.xlsx").write_bytes(b"PK")
    (d / "noext").write_text("raw")

    result = scan_directory(str(d), tmp_vault)
    by_name = {e["filename"]: e["format"] for e in result["unregistered"]}
    assert by_name["doc.PDF"] == "pdf"
    assert by_name["sheet.xlsx"] == "xlsx"
    assert by_name["noext"] == "unknown"


# ---------------------------------------------------------------------------
# Hidden files and ignored names
# ---------------------------------------------------------------------------

def test_hidden_files_excluded(tmp_vault, tmp_path):
    d = tmp_path / "mixed"
    d.mkdir()
    (d / ".hidden").write_text("skip me")
    (d / ".DS_Store").write_bytes(b"")
    (d / "visible.txt").write_text("keep me")

    result = scan_directory(str(d), tmp_vault)
    assert result["total_files"] == 1
    assert result["unregistered"][0]["filename"] == "visible.txt"


def test_ignored_names_excluded(tmp_vault, tmp_path):
    d = tmp_path / "system"
    d.mkdir()
    (d / "Thumbs.db").write_bytes(b"")
    (d / "desktop.ini").write_text("")
    (d / "real.txt").write_text("content")

    result = scan_directory(str(d), tmp_vault)
    assert result["total_files"] == 1


# ---------------------------------------------------------------------------
# Recursive scan
# ---------------------------------------------------------------------------

def test_non_recursive_skips_subdirectories(tmp_vault, tmp_path):
    d = tmp_path / "parent"
    d.mkdir()
    (d / "top.txt").write_text("top")
    sub = d / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep")

    result = scan_directory(str(d), tmp_vault, recursive=False)
    assert result["total_files"] == 1
    assert result["unregistered"][0]["filename"] == "top.txt"


def test_recursive_includes_subdirectories(tmp_vault, tmp_path):
    d = tmp_path / "parent"
    d.mkdir()
    (d / "top.txt").write_text("top")
    sub = d / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep")

    result = scan_directory(str(d), tmp_vault, recursive=True)
    assert result["total_files"] == 2
    filenames = {e["filename"] for e in result["unregistered"]}
    assert filenames == {"top.txt", "deep.txt"}


def test_recursive_skips_hidden_subdirectories(tmp_vault, tmp_path):
    d = tmp_path / "parent"
    d.mkdir()
    (d / "visible.txt").write_text("v")
    hidden_sub = d / ".hidden_sub"
    hidden_sub.mkdir()
    (hidden_sub / "inside.txt").write_text("i")

    result = scan_directory(str(d), tmp_vault, recursive=True)
    assert result["total_files"] == 1


# ---------------------------------------------------------------------------
# Relative path stored in vault node
# ---------------------------------------------------------------------------

def test_relative_path_resolves_against_loci_root(tmp_vault, tmp_path):
    # Simulate a file in loci_root/assets/ (vault_root.parent/assets/) stored with a relative path,
    # matching how save_asset records paths like "assets/<uid>.pdf".
    loci_root = tmp_vault.parent
    assets_dir = loci_root / "assets"
    assets_dir.mkdir(exist_ok=True)
    pdf = assets_dir / "report.pdf"
    pdf.write_bytes(b"%PDF")

    _make_vault_node(tmp_vault, "cc334455", "assets/report.pdf")

    result = scan_directory(str(assets_dir), tmp_vault)
    assert result["total_files"] == 1
    assert len(result["registered"]) == 1
    assert result["registered"][0]["node_uid"] == "cc334455"

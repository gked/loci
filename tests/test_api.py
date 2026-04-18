"""
tests/test_api.py
Tests for api.py: save, delete, patch, check_duplicate, get,
list_items, read_meta, write_meta.
"""

import yaml
import pytest
from pathlib import Path

import api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_raw(vault: Path, name: str, fm: dict, body: str = "") -> Path:
    """Write a raw vault file directly (bypassing api.save)."""
    p = vault / name
    p.write_text(
        "---\n" + yaml.dump(fm, allow_unicode=True) + "---\n\n" + body,
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_vault):
    result = api.save(type="document", title="Test Doc", body="Hello.")
    p = Path(result["path"])
    assert p.exists()
    assert result["type"] == "document"
    assert result["title"] == "Test Doc"
    assert len(result["uid"]) == 8


def test_save_frontmatter_written(tmp_vault):
    result = api.save(
        type="task",
        title="My Task",
        body="Do it.",
        tags=["python"],
        summary="A task.",
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["type"] == "task"
    assert fm["tags"] == ["python"]
    assert fm["summary"] == "A task."


def test_save_invalid_type_raises(tmp_vault):
    with pytest.raises(ValueError):
        api.save(type="invalid", title="T", body="")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_file(tmp_vault):
    result = api.save(type="document", title="To Delete", body="")
    path = result["path"]
    assert Path(path).exists()
    api.delete(path)
    assert not Path(path).exists()


def test_delete_returns_metadata(tmp_vault):
    result = api.save(type="document", title="Del Meta", body="")
    deleted = api.delete(result["path"])
    assert deleted["deleted"] is True
    assert deleted["path"] == result["path"]


def test_delete_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Delete", body="")
    fname = Path(result["path"]).name
    api.delete(fname)  # relative path
    assert not Path(result["path"]).exists()


def test_delete_missing_file_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.delete(str(tmp_vault / "nonexistent.md"))


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------

def test_patch_merges_frontmatter(tmp_vault):
    result = api.save(type="document", title="Patch Me", body="Original.")
    api.patch(result["path"], {"tags": ["updated"], "status": "done"})
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["tags"] == ["updated"]
    assert fm["status"] == "done"
    assert fm["title"] == "Patch Me"  # unchanged field preserved


def test_patch_replaces_body(tmp_vault):
    result = api.save(type="document", title="Body Patch", body="Old body.")
    api.patch(result["path"], {}, body="New body.")
    raw = Path(result["path"]).read_text(encoding="utf-8")
    assert "New body." in raw
    assert "Old body." not in raw


def test_patch_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Patch", body="")
    fname = Path(result["path"]).name
    patched = api.patch(fname, {"title": "Renamed"})
    assert patched["title"] == "Renamed"


def test_patch_returns_metadata(tmp_vault):
    result = api.save(type="document", title="Patch Return", body="")
    patched = api.patch(result["path"], {"tags": ["x"]})
    assert patched["uid"] == result["uid"]
    assert patched["type"] == "document"


# ---------------------------------------------------------------------------
# check_duplicate
# ---------------------------------------------------------------------------

def test_check_duplicate_invalid_type_raises(tmp_vault):
    with pytest.raises(ValueError, match="Unknown type"):
        api.check_duplicate(type="banana", title="T")


def test_check_duplicate_no_match(tmp_vault):
    result = api.check_duplicate(type="document", title="totally unique xyzzy99")
    assert result == {"duplicate": False}


def test_check_duplicate_finds_match(tmp_vault):
    api.save(type="document", title="Duplicate Me", body="")
    result = api.check_duplicate(type="document", title="Duplicate Me")
    assert result["duplicate"] is True
    assert "duplicate-me" in result["name"]


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

def test_get_reads_file(tmp_vault):
    result = api.save(type="document", title="Readable", body="Read this.")
    text = api.get(result["path"])
    assert "Read this." in text
    assert "Readable" in text


def test_get_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Get", body="content")
    fname = Path(result["path"]).name
    text = api.get(fname)
    assert "content" in text


def test_get_missing_file_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.get(str(tmp_vault / "ghost.md"))


def test_get_appends_asset_path_for_large_asset(tmp_vault):
    """When has_asset is True and asset is large/binary, path reference is appended."""
    loci_root = tmp_vault.parent
    uid = "asst0001"

    # Create a fake registry entry and a large binary "asset"
    import asset_registry as ar
    asset_content = b"\x00" * (ar.SIZE_THRESHOLD_BYTES + 1)
    asset_file = ar.assets_dir(loci_root) / f"{uid}.pdf"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.registry_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(asset_content)
    ar.write_registry_entry(loci_root, uid, "pdf", "application/pdf", f"assets/{uid}.pdf")

    # Write vault proxy node with has_asset: true
    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Asset Doc", "has_asset": True},
    )
    text = api.get(str(p))
    assert "asset_path" in text
    assert "application/pdf" in text


def test_get_inlines_small_text_asset(tmp_vault):
    """When has_asset is True and asset is small text, content is inlined."""
    loci_root = tmp_vault.parent
    uid = "asst0002"

    import asset_registry as ar
    asset_content = b"<html>inline content</html>"
    asset_file = ar.assets_dir(loci_root) / f"{uid}.html"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.registry_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(asset_content)
    ar.write_registry_entry(loci_root, uid, "html", "text/html", f"assets/{uid}.html")

    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "HTML Asset", "has_asset": True},
    )
    text = api.get(str(p))
    assert "inline content" in text


# ---------------------------------------------------------------------------
# list_items
# ---------------------------------------------------------------------------

def test_list_items_returns_all_types(tmp_vault):
    api.save(type="document", title="Doc One", body="")
    api.save(type="task", title="Task One", body="")
    result = api.list_items()
    assert "document" in result
    assert "task" in result


def test_list_items_filtered_by_type(tmp_vault):
    api.save(type="document", title="Doc A", body="")
    api.save(type="task", title="Task A", body="")
    result = api.list_items(type="task")
    assert "task" in result
    assert "document" not in result


def test_list_items_empty_vault_returns_empty(tmp_path):
    """list_items on a vault with no .md files returns {}."""
    import os
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    try:
        result = api.list_items()
        assert result == {}
    finally:
        del os.environ["LOCI_VAULT_ROOT"]


# ---------------------------------------------------------------------------
# read_meta / write_meta
# ---------------------------------------------------------------------------

def _make_meta_dir(vault: Path) -> Path:
    meta = vault / "meta"
    meta.mkdir(exist_ok=True)
    for name in ["type-dictionary.md", "tag-dictionary.md", "field-dictionary.md",
                 "relation-dictionary.md", "foreign-definitions.md"]:
        (meta / name).write_text(f"# {name}\n", encoding="utf-8")
    return meta


def test_read_meta_config_returns_vault_root(tmp_vault):
    result = api.read_meta("config")
    assert "vault_root" in result


def test_read_meta_known_file(tmp_vault):
    _make_meta_dir(tmp_vault)
    result = api.read_meta("tag-dictionary")
    assert "tag-dictionary" in result


def test_read_meta_unknown_file_raises(tmp_vault):
    with pytest.raises(ValueError, match="Unknown meta file"):
        api.read_meta("nonexistent-file")


def test_write_meta_writable_file(tmp_vault):
    _make_meta_dir(tmp_vault)
    path = api.write_meta("tag-dictionary", "# updated\nnew content\n")
    assert Path(path).read_text(encoding="utf-8") == "# updated\nnew content\n"


def test_write_meta_readonly_file_raises(tmp_vault):
    with pytest.raises(ValueError, match="read-only"):
        api.write_meta("type-dictionary", "content")


def test_write_meta_unknown_file_raises(tmp_vault):
    with pytest.raises(ValueError):
        api.write_meta("nonexistent", "content")


# ---------------------------------------------------------------------------
# _vault_root error path
# ---------------------------------------------------------------------------

def test_vault_root_raises_when_no_config(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    import vault_init
    monkeypatch.setattr(vault_init, "CONFIG_PATH", tmp_path / "nonexistent.yml")
    with pytest.raises(RuntimeError, match="not configured"):
        api._vault_root()


# ---------------------------------------------------------------------------
# generate_uid
# ---------------------------------------------------------------------------

def test_generate_uid_returns_8_char_hex(tmp_vault):
    import re
    uid = api.generate_uid()
    assert re.fullmatch(r"[0-9a-f]{8}", uid)


# ---------------------------------------------------------------------------
# get — asset error path
# ---------------------------------------------------------------------------

def test_get_asset_missing_appends_error(tmp_vault):
    """has_asset: true but asset not in registry → error note appended."""
    uid = "noasset1"
    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Missing Asset", "has_asset": True},
    )
    text = api.get(str(p))
    assert "asset_error" in text


# ---------------------------------------------------------------------------
# resolve_asset
# ---------------------------------------------------------------------------

def test_resolve_asset(tmp_vault):
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "rslv0001"
    asset_file = ar.assets_dir(loci_root) / f"{uid}.html"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.registry_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(b"<html/>")
    ar.write_registry_entry(loci_root, uid, "html", "text/html", f"assets/{uid}.html")

    result = api.resolve_asset(uid)
    assert result["format"] == "html"
    assert result["size_bytes"] == len(b"<html/>")


# ---------------------------------------------------------------------------
# find_unregistered_assets
# ---------------------------------------------------------------------------

def test_find_unregistered_assets(tmp_vault):
    import asset_registry as ar
    loci_root = tmp_vault.parent
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / "orphan.html").write_bytes(b"data")
    result = api.find_unregistered_assets()
    assert "assets/orphan.html" in result


# ---------------------------------------------------------------------------
# save_asset
# ---------------------------------------------------------------------------

def test_save_asset_full_sequence(tmp_vault):
    result = api.save_asset(
        content=b"<html>hello</html>",
        format="html",
        mime_type="text/html",
        title="My HTML Asset",
        tags=["web"],
    )
    assert "uid" in result
    assert Path(result["asset_path"]).exists()
    assert Path(result["vault_path"]).exists()
    # Intent file cleaned up
    import asset_registry as ar
    loci_root = tmp_vault.parent
    assert not list(ar.pending_dir(loci_root).glob("*.json"))


# ---------------------------------------------------------------------------
# list_items — skipped file paths
# ---------------------------------------------------------------------------

def test_list_items_skips_no_frontmatter(tmp_vault):
    (tmp_vault / "plain.md").write_text("Just plain text\n", encoding="utf-8")
    result = api.list_items()
    all_files = [f for files in result.values() for f in files]
    assert "plain.md" not in all_files


def test_list_items_skips_incomplete_frontmatter(tmp_vault):
    (tmp_vault / "bad-fm.md").write_text("---\ntype: document\n", encoding="utf-8")
    result = api.list_items()
    all_files = [f for files in result.values() for f in files]
    assert "bad-fm.md" not in all_files


def test_list_items_skips_no_type_field(tmp_vault):
    (tmp_vault / "no-type.md").write_text(
        "---\nuid: notype01\ntitle: No Type\n---\n\nbody", encoding="utf-8"
    )
    result = api.list_items()
    all_files = [f for files in result.values() for f in files]
    assert "no-type.md" not in all_files


# ---------------------------------------------------------------------------
# read_meta — FileNotFoundError path
# ---------------------------------------------------------------------------

def test_read_meta_raises_when_file_missing(tmp_vault):
    # meta dir exists but file doesn't
    (tmp_vault / "meta").mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError, match="Meta file not found"):
        api.read_meta("tag-dictionary")


# ---------------------------------------------------------------------------
# fetch_url_metadata
# ---------------------------------------------------------------------------

def test_fetch_url_metadata_og_title():
    from unittest.mock import MagicMock, patch
    mock_resp = MagicMock()
    mock_resp.text = '<html><head><meta property="og:title" content="OG Title"/></head></html>'
    mock_resp.raise_for_status = lambda: None
    with patch("httpx.get", return_value=mock_resp):
        result = api.fetch_url_metadata("https://example.com")
    assert result["title"] == "OG Title"
    assert result["url"] == "https://example.com"


def test_fetch_url_metadata_html_title_fallback():
    from unittest.mock import MagicMock, patch
    mock_resp = MagicMock()
    mock_resp.text = "<html><head><title>HTML Title</title></head></html>"
    mock_resp.raise_for_status = lambda: None
    with patch("httpx.get", return_value=mock_resp):
        result = api.fetch_url_metadata("https://example.com")
    assert result["title"] == "HTML Title"


def test_fetch_url_metadata_og_site_name_and_description():
    from unittest.mock import MagicMock, patch
    mock_resp = MagicMock()
    mock_resp.text = (
        '<html><head>'
        '<meta property="og:title" content="T"/>'
        '<meta property="og:site_name" content="MySite"/>'
        '<meta property="og:description" content="OG Desc"/>'
        '</head></html>'
    )
    mock_resp.raise_for_status = lambda: None
    with patch("httpx.get", return_value=mock_resp):
        result = api.fetch_url_metadata("https://example.com")
    assert result["site_name"] == "MySite"
    assert result["description"] == "OG Desc"


def test_fetch_url_metadata_name_description_fallback():
    from unittest.mock import MagicMock, patch
    mock_resp = MagicMock()
    mock_resp.text = '<html><head><meta name="description" content="Meta Desc"/></head></html>'
    mock_resp.raise_for_status = lambda: None
    with patch("httpx.get", return_value=mock_resp):
        result = api.fetch_url_metadata("https://example.com")
    assert result["description"] == "Meta Desc"


def test_fetch_url_metadata_error_returns_dict():
    from unittest.mock import patch
    with patch("httpx.get", side_effect=Exception("timeout")):
        result = api.fetch_url_metadata("https://example.com")
    assert "error" in result
    assert result["title"] == "https://example.com"


# ---------------------------------------------------------------------------
# read_skill / write_skill
# ---------------------------------------------------------------------------

def test_read_skill_returns_content(tmp_path, monkeypatch):
    skill_dir = tmp_path / "loci-skill" / "loci-save"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Save Skill\n", encoding="utf-8")
    monkeypatch.setattr(api, "__file__", str(tmp_path / "api.py"))
    result = api.read_skill()
    assert result == "# Save Skill\n"


def test_read_skill_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "__file__", str(tmp_path / "api.py"))
    with pytest.raises(FileNotFoundError):
        api.read_skill()


def test_write_skill_writes_content(tmp_path, monkeypatch):
    skill_dir = tmp_path / "loci-skill" / "loci-save"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# original\n", encoding="utf-8")
    monkeypatch.setattr(api, "__file__", str(tmp_path / "api.py"))
    returned_path = api.write_skill("# updated\n")
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "# updated\n"
    assert returned_path == str(skill_dir / "SKILL.md")


def test_write_skill_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "__file__", str(tmp_path / "api.py"))
    with pytest.raises(FileNotFoundError):
        api.write_skill("content")

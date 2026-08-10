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
    result = api.save(type="document", title="Test Doc", body="Hello.", extra_fields={"status": "draft"})
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
        extra_fields={"status": "todo"},
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["type"] == "task"
    assert fm["tags"] == ["python"]
    assert fm["summary"] == "A task."


def test_save_invalid_type_raises(tmp_vault):
    with pytest.raises(ValueError):
        api.save(type="invalid", title="T", body="")


def test_save_missing_required_field_returns_errors(tmp_vault):
    # task requires status; omitting extra_fields must return {"errors": [...]}
    # and must NOT raise KeyError: 'uid'  (regression for api.save graph-index guard)
    result = api.save(type="task", title="Test", body="test body")
    assert "errors" in result
    assert "uid" not in result


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_file(tmp_vault):
    result = api.save(type="document", title="To Delete", body="", extra_fields={"status": "draft"})
    path = result["path"]
    assert Path(path).exists()
    api.delete(path)
    assert not Path(path).exists()


def test_delete_returns_metadata(tmp_vault):
    result = api.save(type="document", title="Del Meta", body="", extra_fields={"status": "draft"})
    deleted = api.delete(result["path"])
    assert deleted["deleted"] is True
    assert deleted["path"] == result["path"]


def test_delete_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Delete", body="", extra_fields={"status": "draft"})
    fname = Path(result["path"]).name
    api.delete(fname)  # relative path
    assert not Path(result["path"]).exists()


def test_delete_missing_file_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.delete(str(tmp_vault / "nonexistent.md"))


def test_delete_by_uid(tmp_vault):
    result = api.save(type="document", title="UID Delete", body="", extra_fields={"status": "draft"})
    api.delete(result["uid"])
    assert not Path(result["path"]).exists()


def test_delete_by_uid_unknown_raises(tmp_vault):
    with pytest.raises(FileNotFoundError, match="deadbeef"):
        api.delete("deadbeef")


def test_delete_directory_raises_not_a_file(tmp_vault):
    (tmp_vault / "somedir").mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError, match="not a file"):
        api.delete("somedir")
    assert (tmp_vault / "somedir").is_dir()


def test_delete_empty_path_does_not_touch_vault_root(tmp_vault):
    with pytest.raises(FileNotFoundError, match="not a file"):
        api.delete("")
    assert tmp_vault.is_dir()


def test_delete_by_uid_stale_graph_path_raises(tmp_vault):
    """A stale graph path pointing at another node's file must not be deleted."""
    victim = api.save(type="document", title="Victim", body="", extra_fields={"status": "draft"})
    stale = api.save(type="document", title="Stale", body="", extra_fields={"status": "draft"})
    # Simulate the stale cache: the file moved away and stale's cached path now
    # points at victim's file. Inject after the rebuild the unlink triggers.
    Path(stale["path"]).unlink()
    g = api.graph.get(tmp_vault)
    g.add_node(stale["uid"], path=victim["path"])

    with pytest.raises(FileNotFoundError, match="stale"):
        api.delete(stale["uid"])
    assert Path(victim["path"]).exists()


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------

def test_patch_merges_frontmatter(tmp_vault):
    result = api.save(type="document", title="Patch Me", body="Original.", extra_fields={"status": "draft"})
    api.patch(result["path"], {"tags": ["updated"], "status": "done"})
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["tags"] == ["updated"]
    assert fm["status"] == "done"
    assert fm["title"] == "Patch Me"  # unchanged field preserved


def test_patch_replaces_body(tmp_vault):
    result = api.save(type="document", title="Body Patch", body="Old body.", extra_fields={"status": "draft"})
    api.patch(result["path"], {}, body="New body.")
    raw = Path(result["path"]).read_text(encoding="utf-8")
    assert "New body." in raw
    assert "Old body." not in raw


def test_patch_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Patch", body="", extra_fields={"status": "draft"})
    fname = Path(result["path"]).name
    patched = api.patch(fname, {"title": "Renamed"})
    assert patched["title"] == "Renamed"


def test_patch_by_uid(tmp_vault):
    result = api.save(type="document", title="UID Patch", body="", extra_fields={"status": "draft"})
    patched = api.patch(result["uid"], {"tags": ["by-uid"], "status": "done"})
    assert patched["uid"] == result["uid"]
    fm = yaml.safe_load(Path(result["path"]).read_text(encoding="utf-8").split("---", 2)[1])
    assert fm["tags"] == ["by-uid"]
    assert fm["status"] == "done"


def test_patch_by_uid_replaces_body(tmp_vault):
    result = api.save(type="document", title="UID Body Patch", body="Old body.", extra_fields={"status": "draft"})
    api.patch(result["uid"], {}, body="New body.")
    raw = Path(result["path"]).read_text(encoding="utf-8")
    assert "New body." in raw
    assert "Old body." not in raw


def test_patch_by_uid_unknown_raises(tmp_vault):
    with pytest.raises(FileNotFoundError, match="deadbeef"):
        api.patch("deadbeef", {"tags": ["x"]})


def test_patch_directory_raises_not_a_file(tmp_vault):
    (tmp_vault / "patchdir").mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError, match="not a file"):
        api.patch("patchdir", {"tags": ["x"]})


def test_patch_by_uid_stale_graph_path_raises(tmp_vault):
    """A stale graph path must not let a patch write into another node's file."""
    victim = api.save(type="document", title="Patch Victim", body="Untouched.", extra_fields={"status": "draft"})
    stale = api.save(type="document", title="Patch Stale", body="", extra_fields={"status": "draft"})
    Path(stale["path"]).unlink()
    g = api.graph.get(tmp_vault)
    g.add_node(stale["uid"], path=victim["path"])

    with pytest.raises(FileNotFoundError, match="stale"):
        api.patch(stale["uid"], {"tags": ["clobbered"]})
    fm = yaml.safe_load(Path(victim["path"]).read_text(encoding="utf-8").split("---", 2)[1])
    assert fm["title"] == "Patch Victim"
    assert fm.get("tags") != ["clobbered"]


def test_patch_returns_metadata(tmp_vault):
    result = api.save(type="document", title="Patch Return", body="", extra_fields={"status": "draft"})
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
    api.save(type="document", title="Duplicate Me", body="", extra_fields={"status": "draft"})
    result = api.check_duplicate(type="document", title="Duplicate Me")
    assert result["duplicate"] is True
    assert "duplicate-me" in result["name"]


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

def test_get_reads_file(tmp_vault):
    result = api.save(type="document", title="Readable", body="Read this.", extra_fields={"status": "draft"})
    text = api.get(result["path"])
    assert "Read this." in text
    assert "Readable" in text


def test_get_relative_path_resolves(tmp_vault):
    result = api.save(type="document", title="Rel Get", body="content", extra_fields={"status": "draft"})
    fname = Path(result["path"]).name
    text = api.get(fname)
    assert "content" in text


def test_get_missing_file_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.get(str(tmp_vault / "ghost.md"))


def test_get_by_uid(tmp_vault):
    result = api.save(type="document", title="UID Lookup", body="found by uid", extra_fields={"status": "draft"})
    uid = result["uid"]
    text = api.get(uid)
    assert "found by uid" in text
    assert "UID Lookup" in text


def test_get_by_uid_unknown_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.get("deadbeef")


def test_get_appends_asset_path_for_large_asset(tmp_vault):
    """When has_asset is a list and asset is large/binary, path reference is appended."""
    loci_root = tmp_vault.parent
    uid = "asst0001"

    import asset_registry as ar
    asset_content = b"\x00" * (ar.SIZE_THRESHOLD_BYTES + 1)
    asset_file = ar.assets_dir(loci_root) / f"{uid}.pdf"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(asset_content)

    has_asset = [{"format": "pdf", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.pdf"}]}]
    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Asset Doc", "has_asset": has_asset},
    )
    text = api.get(str(p))
    assert "asset_path" in text
    assert "application/pdf" in text


def test_get_inlines_small_text_asset(tmp_vault):
    """When has_asset is a list and asset is small text, content is inlined."""
    loci_root = tmp_vault.parent
    uid = "asst0002"

    import asset_registry as ar
    asset_content = b"<html>inline content</html>"
    asset_file = ar.assets_dir(loci_root) / f"{uid}.html"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file.write_bytes(asset_content)

    has_asset = [{"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]}]
    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "HTML Asset", "has_asset": has_asset},
    )
    text = api.get(str(p))
    assert "inline content" in text


# ---------------------------------------------------------------------------
# list_items
# ---------------------------------------------------------------------------

def test_list_items_returns_all_types(tmp_vault):
    api.save(type="document", title="Doc One", body="", extra_fields={"status": "draft"})
    api.save(type="task", title="Task One", body="", extra_fields={"status": "todo"})
    result = api.list_items()
    assert "document" in result
    assert "task" in result


def test_list_items_filtered_by_type(tmp_vault):
    api.save(type="document", title="Doc A", body="", extra_fields={"status": "draft"})
    api.save(type="task", title="Task A", body="", extra_fields={"status": "todo"})
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
    (meta / "ontology.yaml").write_text("types: []\n", encoding="utf-8")
    (meta / "ontology-user.yaml").write_text("types: []\n", encoding="utf-8")
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


def test_read_meta_ontology(tmp_vault):
    _make_meta_dir(tmp_vault)
    result = api.read_meta("ontology")
    assert "types" in result


def test_read_meta_ontology_user(tmp_vault):
    _make_meta_dir(tmp_vault)
    result = api.read_meta("ontology-user")
    assert "types" in result


def test_read_meta_ontology_guide_from_vault(tmp_vault):
    meta = _make_meta_dir(tmp_vault)
    (meta / "ontology-guide.md").write_text("# vault copy\n", encoding="utf-8")
    assert api.read_meta("ontology-guide") == "# vault copy\n"


def test_read_meta_ontology_guide_falls_back_to_references(tmp_vault):
    # Unseeded vault (the Docker case): the canonical copy in references/ answers.
    _make_meta_dir(tmp_vault)
    assert not (tmp_vault / "meta" / "ontology-guide.md").exists()
    result = api.read_meta("ontology-guide")
    assert "# The Ontology" in result


def test_write_meta_writable_file(tmp_vault):
    _make_meta_dir(tmp_vault)
    path = api.write_meta("tag-dictionary", "# updated\nnew content\n")
    assert Path(path).read_text(encoding="utf-8") == "# updated\nnew content\n"


def test_write_meta_ontology_user(tmp_vault):
    _make_meta_dir(tmp_vault)
    content = "types:\n  - name: recipe\n    extends: procedure\n"
    path = api.write_meta("ontology-user", content)
    assert Path(path).read_text(encoding="utf-8") == content


def test_write_meta_readonly_file_raises(tmp_vault):
    with pytest.raises(ValueError, match="read-only"):
        api.write_meta("type-dictionary", "content")


def test_write_meta_ontology_readonly_raises(tmp_vault):
    with pytest.raises(ValueError, match="read-only"):
        api.write_meta("ontology", "content")


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
    """has_asset list with unreachable local location → error note appended."""
    uid = "noasset1"
    has_asset = [{"format": "pdf", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.pdf"}]}]
    p = _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Missing Asset", "has_asset": has_asset},
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
    asset_file.write_bytes(b"<html/>")

    has_asset = [{"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Asset Doc", "has_asset": has_asset, "status": "draft"},
    )

    result = api.resolve_asset(uid)
    assert result["format"] == "html"
    assert result["size_bytes"] == len(b"<html/>")


def test_resolve_asset_uid_not_in_graph_raises(tmp_vault):
    """UID with no vault node raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="No vault node"):
        api.resolve_asset("deadbeef")


def test_resolve_asset_has_asset_boolean_raises(tmp_vault):
    """Node with legacy has_asset: true (boolean) raises FileNotFoundError."""
    uid = "legc0001"
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Legacy", "has_asset": True},
    )
    with pytest.raises(FileNotFoundError, match="has no asset locations"):
        api.resolve_asset(uid)


def test_resolve_asset_has_asset_missing_raises(tmp_vault):
    """Node with no has_asset field raises FileNotFoundError."""
    uid = "nohas001"
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "No Asset"},
    )
    with pytest.raises(FileNotFoundError, match="has no asset locations"):
        api.resolve_asset(uid)


def test_resolve_asset_format_not_found_raises(tmp_vault):
    """Requesting a format not in has_asset raises ValueError."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "fmtnf001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / f"{uid}.html").write_bytes(b"<html/>")

    has_asset = [{"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "HTML Only Asset", "has_asset": has_asset},
    )
    with pytest.raises(ValueError, match="No 'pdf' format"):
        api.resolve_asset(uid, format="pdf")


def test_resolve_asset_all_locations_fail_raises(tmp_vault):
    """All locations unreachable raises FileNotFoundError mentioning 'not reachable'."""
    uid = "noreac01"
    has_asset = [{"format": "pdf", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.pdf"}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Gone Asset", "has_asset": has_asset},
    )
    with pytest.raises(FileNotFoundError, match="not reachable"):
        api.resolve_asset(uid)


def test_resolve_asset_selects_primary_variant(tmp_vault):
    """When no format specified, the primary variant is preferred over others."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "prim0001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / f"{uid}.html").write_bytes(b"<html/>")
    (ar.assets_dir(loci_root) / f"{uid}.pdf").write_bytes(b"%PDF")

    has_asset = [
        {"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]},
        {"format": "pdf", "locations": [{"scheme": "local", "path": f"assets/{uid}.pdf"}]},
    ]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Multi-format Asset", "has_asset": has_asset},
    )
    result = api.resolve_asset(uid)
    assert result["format"] == "html"


def test_resolve_asset_falls_back_to_first_when_no_primary(tmp_vault):
    """When no variant has primary=True, the first valid variant is used."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "nopri001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / f"{uid}.html").write_bytes(b"<html/>")

    has_asset = [{"format": "html", "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "No-primary Asset", "has_asset": has_asset},
    )
    result = api.resolve_asset(uid)
    assert result["format"] == "html"


def test_resolve_asset_by_explicit_format(tmp_vault):
    """Requesting a specific format by name returns that variant, not the primary."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "fmtok001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / f"{uid}.html").write_bytes(b"<html/>")
    (ar.assets_dir(loci_root) / f"{uid}.pdf").write_bytes(b"%PDF")

    has_asset = [
        {"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]},
        {"format": "pdf", "locations": [{"scheme": "local", "path": f"assets/{uid}.pdf"}]},
    ]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "PDF Asset", "has_asset": has_asset},
    )
    result = api.resolve_asset(uid, format="pdf")
    assert result["format"] == "pdf"


# ---------------------------------------------------------------------------
# find_unregistered_assets
# ---------------------------------------------------------------------------

def test_find_unregistered_no_assets_dir(tmp_vault):
    """No assets/ directory → returns []."""
    result = api.find_unregistered_assets()
    assert result == []


def test_find_unregistered_assets_returns_orphan(tmp_vault):
    """Files in assets/ with no vault node registration are returned."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / "orphan.html").write_bytes(b"data")
    result = api.find_unregistered_assets()
    assert "assets/orphan.html" in result


def test_find_unregistered_excludes_registered_files(tmp_vault):
    """Files claimed by a vault node's has_asset list are not returned."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "reg00001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / f"{uid}.html").write_bytes(b"<html/>")

    has_asset = [{"format": "html", "primary": True, "locations": [{"scheme": "local", "path": f"assets/{uid}.html"}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Registered Asset", "has_asset": has_asset},
    )
    result = api.find_unregistered_assets()
    assert f"assets/{uid}.html" not in result


def test_find_unregistered_ignores_dotfiles(tmp_vault):
    """Dotfiles in assets/ are always excluded."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    (ar.assets_dir(loci_root) / ".tmp_draft.pdf").write_bytes(b"%PDF")
    result = api.find_unregistered_assets()
    assert not any(".tmp_draft.pdf" in r for r in result)


def test_find_unregistered_handles_absolute_loc_path(tmp_vault):
    """Absolute paths in loc.path are normalised to relative and recognised as registered."""
    import asset_registry as ar
    loci_root = tmp_vault.parent
    uid = "absp0001"
    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    asset_file = ar.assets_dir(loci_root) / f"{uid}.pdf"
    asset_file.write_bytes(b"%PDF")

    has_asset = [{"format": "pdf", "primary": True, "locations": [{"scheme": "local", "path": str(asset_file)}]}]
    _write_raw(
        tmp_vault, f"{uid}-doc.md",
        {"uid": uid, "type": "document", "title": "Abs Path Asset", "has_asset": has_asset},
    )
    result = api.find_unregistered_assets()
    assert f"assets/{uid}.pdf" not in result


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
    # Vault node has has_asset as list with local scheme
    raw = Path(result["vault_path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert isinstance(fm.get("has_asset"), list)
    assert fm["has_asset"][0]["locations"][0]["scheme"] == "local"


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
    skill_dir = tmp_path / "skills" / "loci-save"
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
    skill_dir = tmp_path / "skills" / "loci-save"
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

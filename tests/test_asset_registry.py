"""
tests/test_asset_registry.py
Tests for tools/asset_registry.py: write_registry_entry, append_manifest,
write_intent, find_unregistered, resolve, and recover_pending.
"""

import json
import yaml
import pytest
from pathlib import Path

import asset_registry as ar


@pytest.fixture
def loci_root(tmp_path):
    """Minimal loci root with required subdirectories."""
    root = tmp_path / "loci"
    root.mkdir()
    ar.assets_dir(root).mkdir(parents=True)
    ar.registry_dir(root).mkdir(parents=True)
    ar.pending_dir(root).mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# write_registry_entry
# ---------------------------------------------------------------------------

def test_write_registry_entry_creates_yaml(loci_root):
    ar.write_registry_entry(loci_root, "abc12345", "html", "text/html", "assets/abc12345.html")
    reg = ar.registry_dir(loci_root) / "abc12345.yaml"
    assert reg.exists()
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    assert data["uid"] == "abc12345"
    assert len(data["files"]) == 1
    f = data["files"][0]
    assert f["format"] == "html"
    assert f["mime_type"] == "text/html"
    assert f["primary"] is True
    assert f["locations"][0]["scheme"] == "asset-vault"
    assert f["locations"][0]["path"] == "assets/abc12345.html"


def test_write_registry_entry_is_idempotent(loci_root):
    ar.write_registry_entry(loci_root, "abc12345", "html", "text/html", "assets/abc12345.html")
    ar.write_registry_entry(loci_root, "abc12345", "html", "text/html", "assets/abc12345.html")
    reg = ar.registry_dir(loci_root) / "abc12345.yaml"
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    assert len(data["files"]) == 1


# ---------------------------------------------------------------------------
# append_manifest
# ---------------------------------------------------------------------------

def test_append_manifest_creates_file(loci_root):
    ar.append_manifest(loci_root, "assets/abc12345.html")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    assert "assets/abc12345.html" in text


def test_append_manifest_updates_scheme_counts(loci_root):
    ar.append_manifest(loci_root, "assets/aaa.html")
    ar.append_manifest(loci_root, "assets/bbb.png")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    text = manifest.read_text(encoding="utf-8")
    assert "# asset-vault: 2" in text


def test_append_manifest_deduplicates(loci_root):
    ar.append_manifest(loci_root, "assets/aaa.html")
    ar.append_manifest(loci_root, "assets/aaa.html")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    entries = [
        l for l in manifest.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    assert entries.count("assets/aaa.html") == 1


def test_append_manifest_preserves_existing_entries(loci_root):
    ar.append_manifest(loci_root, "assets/first.html")
    ar.append_manifest(loci_root, "assets/second.pdf")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    text = manifest.read_text(encoding="utf-8")
    assert "assets/first.html" in text
    assert "assets/second.pdf" in text


def test_append_manifest_s3_scheme(loci_root):
    ar.append_manifest(loci_root, "s3://my-bucket/loci/abc.pdf")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    text = manifest.read_text(encoding="utf-8")
    assert "# s3: 1" in text
    assert "s3://my-bucket/loci/abc.pdf" in text


def test_append_manifest_nas_scheme(loci_root):
    ar.append_manifest(loci_root, "nas:/shares/loci/abc.pdf")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    text = manifest.read_text(encoding="utf-8")
    assert "# nas: 1" in text


def test_append_manifest_http_scheme(loci_root):
    ar.append_manifest(loci_root, "https://cdn.example.com/abc.pdf")
    manifest = ar.registry_dir(loci_root) / "manifest.txt"
    text = manifest.read_text(encoding="utf-8")
    assert "# http: 1" in text


# ---------------------------------------------------------------------------
# write_intent
# ---------------------------------------------------------------------------

def test_write_intent_creates_json(loci_root):
    vault_node = {"title": "T", "summary": None, "tags": [], "domains": [], "relations": []}
    intent_path = ar.write_intent(
        loci_root, "uid00001", "html", "text/html",
        "/tmp/.uid00001.html.tmp", "assets/uid00001.html",
        "/vault/doc.md", vault_node,
    )
    assert intent_path.exists()
    data = json.loads(intent_path.read_text(encoding="utf-8"))
    assert data["uid"] == "uid00001"
    assert data["format"] == "html"
    assert data["mime_type"] == "text/html"
    assert data["vault_node"] == vault_node


# ---------------------------------------------------------------------------
# find_unregistered
# ---------------------------------------------------------------------------

def test_find_unregistered_no_assets_dir(tmp_path):
    root = tmp_path / "loci"
    root.mkdir()
    assert ar.find_unregistered(root) == []


def test_find_unregistered_all_registered(loci_root):
    (ar.assets_dir(loci_root) / "abc12345.html").write_bytes(b"<html/>")
    ar.append_manifest(loci_root, "assets/abc12345.html")
    assert ar.find_unregistered(loci_root) == []


def test_find_unregistered_returns_unlisted_files(loci_root):
    (ar.assets_dir(loci_root) / "abc12345.html").write_bytes(b"<html/>")
    # No manifest entry for this file
    result = ar.find_unregistered(loci_root)
    assert "assets/abc12345.html" in result


def test_find_unregistered_ignores_dotfiles(loci_root):
    (ar.assets_dir(loci_root) / ".tmp123.html").write_bytes(b"temp")
    assert ar.find_unregistered(loci_root) == []


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

def test_resolve_happy_path(loci_root):
    uid = "res00001"
    asset_path = ar.assets_dir(loci_root) / f"{uid}.html"
    asset_path.write_bytes(b"<html>hello</html>")
    ar.write_registry_entry(loci_root, uid, "html", "text/html", f"assets/{uid}.html")

    result = ar.resolve(loci_root, uid)
    assert result["format"] == "html"
    assert result["mime_type"] == "text/html"
    assert result["size_bytes"] == len(b"<html>hello</html>")
    assert result["path"] == str(asset_path)


def test_resolve_missing_registry_raises(loci_root):
    with pytest.raises(FileNotFoundError, match="No registry entry"):
        ar.resolve(loci_root, "missing1")


def test_resolve_format_not_found_raises(loci_root):
    uid = "fmt00001"
    asset_path = ar.assets_dir(loci_root) / f"{uid}.html"
    asset_path.write_bytes(b"content")
    ar.write_registry_entry(loci_root, uid, "html", "text/html", f"assets/{uid}.html")

    with pytest.raises(ValueError, match="No 'pdf' format"):
        ar.resolve(loci_root, uid, fmt="pdf")


def test_resolve_file_missing_raises(loci_root):
    uid = "gone0001"
    # Write registry entry but don't create the actual file
    ar.write_registry_entry(loci_root, uid, "html", "text/html", f"assets/{uid}.html")

    with pytest.raises(FileNotFoundError, match="not reachable"):
        ar.resolve(loci_root, uid)


def test_resolve_empty_files_list_raises(loci_root):
    """Registry entry with an empty files list → FileNotFoundError (no files)."""
    import yaml
    uid = "empty001"
    entry = {"uid": uid, "registered_at": "2026-01-01T00:00:00Z", "files": []}
    reg_path = ar.registry_dir(loci_root) / f"{uid}.yaml"
    reg_path.write_text(yaml.dump(entry), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="has no files"):
        ar.resolve(loci_root, uid)


def test_resolve_physical_only_raises_with_clear_message(loci_root):
    """Physical-only registry entry (files=[], physical=[...]) → descriptive error."""
    uid = "phys0001"
    ar.write_physical_entry(
        loci_root, uid,
        [{"format": "paperback", "location": "Bookshelf A3"}],
    )
    with pytest.raises(FileNotFoundError, match="physical-only"):
        ar.resolve(loci_root, uid)


def test_resolve_falls_back_to_first_file_when_no_primary(loci_root):
    """Registry entry with no primary flag → fall back to files[0]."""
    import yaml
    uid = "noprim01"
    asset_path = ar.assets_dir(loci_root) / f"{uid}.html"
    asset_path.write_bytes(b"content")
    # Write a registry entry without the primary flag
    entry = {
        "uid": uid,
        "registered_at": "2026-01-01T00:00:00Z",
        "files": [
            {
                "format": "html",
                "mime_type": "text/html",
                # no "primary" key
                "locations": [
                    {"scheme": "asset-vault", "path": f"assets/{uid}.html", "priority": 1}
                ],
            }
        ],
    }
    reg_path = ar.registry_dir(loci_root) / f"{uid}.yaml"
    reg_path.write_text(yaml.dump(entry), encoding="utf-8")

    result = ar.resolve(loci_root, uid)
    assert result["format"] == "html"


# ---------------------------------------------------------------------------
# write_physical_entry
# ---------------------------------------------------------------------------

def test_write_physical_entry_creates_yaml(loci_root):
    instances = [{"format": "paperback", "location": "Bookshelf A3", "condition": "good"}]
    ar.write_physical_entry(loci_root, "phys0002", instances)
    reg = ar.registry_dir(loci_root) / "phys0002.yaml"
    assert reg.exists()
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    assert data["uid"] == "phys0002"
    assert data["files"] == []
    assert len(data["physical"]) == 1
    assert data["physical"][0]["format"] == "paperback"
    assert data["physical"][0]["location"] == "Bookshelf A3"


def test_write_physical_entry_multiple_instances(loci_root):
    instances = [
        {"format": "coin", "location": "Safe, drawer 2", "quantity": 3,
         "attributes": {"metal": "gold", "weight_troy_oz": 1}},
        {"format": "coin", "location": "Bank vault", "quantity": 1},
    ]
    ar.write_physical_entry(loci_root, "phys0003", instances)
    data = yaml.safe_load(
        (ar.registry_dir(loci_root) / "phys0003.yaml").read_text(encoding="utf-8")
    )
    assert len(data["physical"]) == 2
    assert data["physical"][0]["attributes"]["metal"] == "gold"


# ---------------------------------------------------------------------------
# add_physical_instance
# ---------------------------------------------------------------------------

def test_add_physical_instance_to_existing_digital_entry(loci_root):
    uid = "dual0001"
    ar.write_registry_entry(loci_root, uid, "epub", "application/epub+zip", f"assets/{uid}.epub")
    ar.add_physical_instance(loci_root, uid, {"format": "paperback", "location": "Bookshelf B1"})

    data = yaml.safe_load(
        (ar.registry_dir(loci_root) / f"{uid}.yaml").read_text(encoding="utf-8")
    )
    assert len(data["files"]) == 1
    assert len(data["physical"]) == 1
    assert data["physical"][0]["format"] == "paperback"


def test_add_physical_instance_appends_to_existing_physical(loci_root):
    uid = "dual0002"
    ar.write_physical_entry(loci_root, uid, [{"format": "hardcover", "location": "Office shelf"}])
    ar.add_physical_instance(loci_root, uid, {"format": "paperback", "location": "Bookshelf A3"})

    data = yaml.safe_load(
        (ar.registry_dir(loci_root) / f"{uid}.yaml").read_text(encoding="utf-8")
    )
    assert len(data["physical"]) == 2


def test_add_physical_instance_creates_entry_if_missing(loci_root):
    uid = "dual0003"
    ar.add_physical_instance(loci_root, uid, {"format": "vehicle", "location": "Home garage"})

    reg = ar.registry_dir(loci_root) / f"{uid}.yaml"
    assert reg.exists()
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    assert data["uid"] == uid
    assert data["physical"][0]["format"] == "vehicle"


# ---------------------------------------------------------------------------
# recover_pending
# ---------------------------------------------------------------------------

def _make_intent(loci_root: Path, uid: str, asset_content: bytes = b"data") -> dict:
    """Set up a complete pending intent. Returns paths dict."""
    asset_tmp = ar.assets_dir(loci_root) / f".{uid}.html.tmp"
    asset_rel = f"assets/{uid}.html"
    vault_path = loci_root / "vault" / f"{uid}-doc.md"
    vault_node = {"title": "Doc", "summary": None, "tags": [], "domains": [], "relations": []}

    ar.write_intent(
        loci_root, uid, "html", "text/html",
        str(asset_tmp), asset_rel, str(vault_path), vault_node,
    )
    return {"asset_tmp": asset_tmp, "asset_rel": asset_rel, "vault_path": vault_path}


def _proxy_writer(vault_root, uid, node):
    """Minimal vault proxy writer for recovery tests."""
    vault_root.mkdir(parents=True, exist_ok=True)
    p = vault_root / f"{uid}-doc.md"
    p.write_text(f"---\nuid: {uid}\ntype: document\ntitle: Doc\n---\n", encoding="utf-8")
    return str(p)


def test_recover_pending_no_pending_dir(tmp_path):
    root = tmp_path / "loci"
    root.mkdir()
    vault_root = root / "vault"
    assert ar.recover_pending(root, vault_root, _proxy_writer) == []


def test_recover_pending_crash_before_any_file(loci_root):
    """Intent exists but neither tmp nor final asset was written — clean up intent."""
    uid = "cr000001"
    paths = _make_intent(loci_root, uid)
    # Neither tmp nor final exists — nothing to recover
    recovered = ar.recover_pending(loci_root, loci_root / "vault", _proxy_writer)
    assert uid not in recovered
    assert not (ar.pending_dir(loci_root) / f"{uid}.json").exists()


def test_recover_pending_crash_after_tmp_write(loci_root):
    """Crash after staging to tmp — should rename, write registry, manifest, vault node."""
    uid = "cr000002"
    paths = _make_intent(loci_root, uid)
    # Simulate crash after step 2 (tmp written, rename not done)
    paths["asset_tmp"].write_bytes(b"<html>content</html>")

    vault_root = loci_root / "vault"
    recovered = ar.recover_pending(loci_root, vault_root, _proxy_writer)

    assert uid in recovered
    # tmp renamed to final
    assert (loci_root / paths["asset_rel"]).exists()
    assert not paths["asset_tmp"].exists()
    # registry written
    assert (ar.registry_dir(loci_root) / f"{uid}.yaml").exists()
    # manifest updated
    manifest_text = (ar.registry_dir(loci_root) / "manifest.txt").read_text()
    assert paths["asset_rel"] in manifest_text
    # vault proxy written
    assert (vault_root / f"{uid}-doc.md").exists()
    # intent deleted
    assert not (ar.pending_dir(loci_root) / f"{uid}.json").exists()


def test_recover_pending_crash_after_rename(loci_root):
    """Crash after rename (final exists, no registry) — should write registry onwards."""
    uid = "cr000003"
    paths = _make_intent(loci_root, uid)
    # Final asset already exists (rename already done)
    (loci_root / paths["asset_rel"]).write_bytes(b"content")

    vault_root = loci_root / "vault"
    recovered = ar.recover_pending(loci_root, vault_root, _proxy_writer)

    assert uid in recovered
    assert (ar.registry_dir(loci_root) / f"{uid}.yaml").exists()
    assert not (ar.pending_dir(loci_root) / f"{uid}.json").exists()


def test_recover_pending_idempotent_manifest(loci_root):
    """If manifest already contains the entry, no duplicate is added."""
    uid = "cr000004"
    paths = _make_intent(loci_root, uid)
    (loci_root / paths["asset_rel"]).write_bytes(b"content")
    # Pre-populate manifest
    ar.append_manifest(loci_root, paths["asset_rel"])

    ar.recover_pending(loci_root, loci_root / "vault", _proxy_writer)

    entries = [
        l for l in (ar.registry_dir(loci_root) / "manifest.txt").read_text().splitlines()
        if l.strip() and not l.startswith("#")
    ]
    assert entries.count(paths["asset_rel"]) == 1

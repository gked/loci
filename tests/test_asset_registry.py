"""
tests/test_asset_registry.py
Tests for tools/asset_registry.py: write_intent and recover_pending.
"""

import json
import pytest
from pathlib import Path

from loci.tools import asset_registry as ar


@pytest.fixture
def loci_root(tmp_path):
    """Minimal loci root with required subdirectories."""
    root = tmp_path / "loci"
    root.mkdir()
    ar.assets_dir(root).mkdir(parents=True)
    ar.pending_dir(root).mkdir(parents=True)
    return root


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
    """Crash after staging to tmp — should rename tmp to final and write vault node."""
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
    # vault proxy written
    assert (vault_root / f"{uid}-doc.md").exists()
    # intent deleted
    assert not (ar.pending_dir(loci_root) / f"{uid}.json").exists()


def test_recover_pending_crash_after_rename(loci_root):
    """Crash after rename (final exists, vault proxy not yet written)."""
    uid = "cr000003"
    paths = _make_intent(loci_root, uid)
    # Final asset already exists (rename already done)
    (loci_root / paths["asset_rel"]).write_bytes(b"content")

    vault_root = loci_root / "vault"
    recovered = ar.recover_pending(loci_root, vault_root, _proxy_writer)

    assert uid in recovered
    assert not (ar.pending_dir(loci_root) / f"{uid}.json").exists()

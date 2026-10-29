"""
asset_registry.py
Manages Loci asset write sequences: path helpers, intent files and crash recovery.

Folder structure (siblings under ~/Nextcloud/loci/):
  assets/                  ← binary/rich files (local storage)
    .pending/              ← intent files for crash recovery

Where an asset lives is recorded in the node's `has_asset` frontmatter, not here.
"""

import json
from pathlib import Path


SIZE_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def assets_dir(loci_root: Path) -> Path:
    return loci_root / "assets"


def pending_dir(loci_root: Path) -> Path:
    return assets_dir(loci_root) / ".pending"


# ---------------------------------------------------------------------------
# Write sequence helpers
# ---------------------------------------------------------------------------

def write_intent(
    loci_root: Path,
    uid: str,
    fmt: str,
    mime_type: str,
    asset_tmp_path: str,
    asset_rel_path: str,
    vault_path: str,
    vault_node: dict,
) -> Path:
    """Write .pending/<uid>.json intent file. Returns intent path."""
    pd = pending_dir(loci_root)
    pd.mkdir(parents=True, exist_ok=True)

    intent = {
        "uid": uid,
        "format": fmt,
        "mime_type": mime_type,
        "asset_tmp_path": asset_tmp_path,
        "asset_rel_path": asset_rel_path,
        "vault_path": vault_path,
        "vault_node": vault_node,
    }

    intent_path = pd / f"{uid}.json"
    intent_path.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    return intent_path


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------

def recover_pending(loci_root: Path, vault_root: Path, write_vault_proxy_fn) -> list:
    """
    On startup: scan .pending/ and resume any interrupted write sequences.

    write_vault_proxy_fn(vault_root, uid, vault_node) -> str
        Called to (re)write the vault proxy node; should return the vault file path.
        vault_node carries the node's 'type' and the 'extra_fields' the live save
        would have written; older intents have only a 'has_asset' list.

    Returns list of UIDs that were recovered.
    """
    pd = pending_dir(loci_root)
    if not pd.exists():
        return []

    recovered = []
    for intent_file in pd.glob("*.json"):
        intent = json.loads(intent_file.read_text(encoding="utf-8"))
        uid = intent["uid"]
        fmt = intent["format"]
        mime_type = intent["mime_type"]
        asset_tmp = Path(intent["asset_tmp_path"])
        asset_rel = intent["asset_rel_path"]
        asset_final = loci_root / asset_rel
        vault_path = Path(intent["vault_path"])
        vault_node = intent["vault_node"]

        if not asset_tmp.exists() and not asset_final.exists():
            # Crash before any file was written — nothing to recover
            intent_file.unlink()
            continue

        # Step 3: rename tmp → final
        if asset_tmp.exists() and not asset_final.exists():
            asset_tmp.rename(asset_final)

        # Ensure vault_node carries has_asset (backward compat for old intents)
        if "has_asset" not in vault_node:
            vault_node = dict(vault_node)
            vault_node["has_asset"] = [
                {
                    "format": fmt,
                    "mime_type": mime_type,
                    "primary": True,
                    "locations": [{"scheme": "local", "path": asset_rel}],
                }
            ]

        # Step 6: write vault proxy node
        if not vault_path.exists():
            write_vault_proxy_fn(vault_root, uid, vault_node)

        # Step 7: delete intent file
        intent_file.unlink()
        recovered.append(uid)

    return recovered

"""
vault_init.py
Initializes the Loci vault folder structure and config file.

Run this once on first setup, or to repair a missing vault structure.
Config is stored at <project_root>/config.yml
"""

import os
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


CONFIG_PATH = Path(__file__).parent.parent / "config.yml"
REFERENCES_DIR = Path(__file__).parent.parent / "loci-skill" / "references"

META_VERSION = 1

VAULT_FOLDERS = [
    "documents",
    "articles",
    "bookmarks",
    "conversations",
    "projects",
    "tasks",
    "events",
    "entities",
    "procedures",
    "topics",
    "references",
    "meta",
]

META_FILES = [
    "type-dictionary.md",
    "tag-dictionary.md",
    "field-dictionary.md",
    "relation-dictionary.md",
    "foreign-definitions.md",
]


def load_config() -> Optional[dict]:
    """Load existing config if present. LOCI_VAULT_ROOT env var takes precedence."""
    vault_root_env = os.environ.get("LOCI_VAULT_ROOT")
    if vault_root_env:
        return {"vault_root": vault_root_env}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return None


def save_config(config: dict) -> None:
    """Save config to <project_root>/config.yml"""
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Config saved to {CONFIG_PATH}")


def create_vault_structure(vault_root: Path) -> None:
    """Create vault folder structure, asset storage, and seed meta files."""
    vault_root.mkdir(parents=True, exist_ok=True)

    for folder in VAULT_FOLDERS:
        folder_path = vault_root / folder
        folder_path.mkdir(exist_ok=True)
        print(f"  Created: {folder_path}")

    # Asset storage lives alongside vault/, not inside it
    loci_root = vault_root.parent
    for folder in ["assets", "asset-registry/.pending"]:
        p = loci_root / folder
        p.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {p}")

    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        if not dest.exists():
            src = REFERENCES_DIR / filename
            dest.write_text(src.read_text())
            print(f"  Seeded: {dest}")


def setup_interactive() -> dict:
    """Interactive first-run setup flow."""
    print("\nLoci is not configured yet. Let's set it up.\n")

    default_vault = Path(__file__).parent.parent / "knowledge-vault"
    vault_input = input(f"Where should the vault live? (default: {default_vault}): ").strip()
    vault_root = Path(vault_input) if vault_input else default_vault

    remote = input("rclone remote name for sync (e.g. nextcloud, dropbox — leave blank to skip): ").strip()
    remote_path = ""
    if remote:
        remote_path = input("Path on the remote (default: loci): ").strip() or "loci"

    config = {
        "vault_root": str(vault_root),
        "sync_remote": remote or None,
        "sync_remote_path": remote_path or "loci",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "meta_version": META_VERSION,
    }

    return config


def check_meta_version() -> None:
    """
    Warn at startup if the vault's meta_version is older than META_VERSION.
    Skipped silently when running via LOCI_VAULT_ROOT (Docker), since there
    is no config.yml to read meta_version from.
    """
    if os.environ.get("LOCI_VAULT_ROOT"):
        return  # Docker / env-var mode: no config.yml to inspect
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    vault_meta_version = config.get("meta_version")
    if vault_meta_version is not None and vault_meta_version < META_VERSION:
        print(
            f"WARNING: vault meta_version={vault_meta_version} is older than "
            f"server META_VERSION={META_VERSION}. "
            "Run `python tools/vault_init.py --force` to re-seed meta files.",
            file=sys.stderr,
        )


def init(force: bool = False) -> dict:
    """
    Initialize Loci. Returns the active config.

    Args:
        force: If True, re-run setup even if config exists.
    """
    existing = load_config()

    if existing and not force:
        print(f"Loci already configured. Vault root: {existing['vault_root']}")
        vault_root = Path(existing["vault_root"])
        print("Ensuring vault structure is complete...")
        create_vault_structure(vault_root)
        print("Done.")
        return existing

    config = setup_interactive()
    save_config(config)

    vault_root = Path(config["vault_root"])
    print(f"\nCreating vault structure at {vault_root}...")
    create_vault_structure(vault_root)

    print(f"\nLoci is ready. Vault at: {vault_root}\n")
    return config


if __name__ == "__main__":
    force = "--force" in sys.argv
    init(force=force)

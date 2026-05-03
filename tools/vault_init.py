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

META_VERSION = 5

VAULT_FOLDERS = [
    "meta",
]

# Reseeded on every META_VERSION bump.
META_FILES = [
    "type-dictionary.md",
    "tag-dictionary.md",
    "field-dictionary.md",
    "relation-dictionary.md",    # human-readable reference; kept alongside the machine-readable registry
    "relation-dictionary.yaml",
    "foreign-definitions.md",
    "ontology.yaml",
]

# Seeded once on first setup, never overwritten — user owns these.
USER_META_FILES = [
    "ontology-user.yaml",
    "relation-dictionary-user.yaml",
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

    # Staging folder lives alongside vault/, not inside it
    stage_root = loci_root / "loci-stage"
    for stage_folder in [stage_root, stage_root / "files", stage_root / "unresolved"]:
        stage_folder.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {stage_folder}")

    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        if not dest.exists():
            dest.write_text(src.read_text())
            print(f"  Seeded: {dest}")

    for filename in USER_META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        if not dest.exists():
            dest.write_text(src.read_text())
            print(f"  Seeded (user): {dest}")


def reseed_meta(vault_root: Path) -> None:
    """Force overwrite canonical meta files from loci-skill/references/.
    USER_META_FILES are never touched — the user owns those."""
    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        dest.write_text(src.read_text())
        print(f"  Re-seeded: {dest}")


def reseed_meta(vault_root: Path) -> None:
    """Force overwrite all meta files from loci-skill/references/."""
    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        dest.write_text(src.read_text())
        print(f"  Re-seeded: {dest}")


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


def check_meta_version() -> str | None:
    """
    Auto-reseed meta files at server startup if vault meta_version is older
    than META_VERSION. Returns a notice string if reseeding occurred so the
    caller can surface it to the user; returns None otherwise.
    Skipped silently when running via LOCI_VAULT_ROOT (Docker).
    """
    if os.environ.get("LOCI_VAULT_ROOT"):
        return None  # Docker / env-var mode: no config.yml to inspect
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    vault_meta_version = config.get("meta_version")
    if vault_meta_version is None or vault_meta_version < META_VERSION:
        vault_root = Path(config["vault_root"])
        reseed_meta(vault_root)
        config["meta_version"] = META_VERSION
        save_config(config)
        from_version = f"v{vault_meta_version}" if vault_meta_version is not None else "unversioned"
        return (
            f"Vault meta files were automatically updated from {from_version} "
            f"to v{META_VERSION}. No action needed."
        )
    return None


def init(force: bool = False) -> dict:
    """
    Initialize Loci. Returns the active config.

    Args:
        force: If True, re-seed all meta files from references/ and bump
               meta_version in config. Does not re-run interactive setup.
    """
    existing = load_config()

    if existing and force:
        vault_root = Path(existing["vault_root"])
        print(f"Re-seeding meta files at {vault_root / 'meta'}...")
        reseed_meta(vault_root)
        existing["meta_version"] = META_VERSION
        save_config(existing)
        print("Done.")
        return existing

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


if __name__ == "__main__":  # pragma: no cover
    force = "--force" in sys.argv
    init(force=force)

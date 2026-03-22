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

VAULT_FOLDERS = [
    "notes",
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

TYPE_DICTIONARY = """\
# Loci Type Dictionary
# Canonical type vocabulary — edit with care.
# The save skill reads this file at runtime.

note         — freeform thought or observation
article      — external content consumed and captured (format carried by tag: #book, #article, #paper, #video)
bookmark     — saved URL with light metadata only; use article when capturing full content
conversation — saved LLM or human conversation (has turns, participants, model/person)
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, company, org, institution (subtype by tag: #person, #company, #organization, #institution)
procedure    — repeatable process with ordered steps and expected outcome (subtype by tag: #recipe, #workout, #protocol, #playbook, #tutorial)
topic        — organizing hub for a subject area
reference    — pointer to external content (hybrid ownership model)
"""

TAG_DICTIONARY = """\
# Loci Tag Dictionary
# Freeform tag vocabulary — consulted by the save skill at ingestion.
# Purpose: keep tags consistent across items saved over time.
# When tagging, prefer an existing tag over a synonym.
# Add new tags here when a concept recurs and deserves a stable label.
#
# Format: one tag per line, lowercase, hyphenated.
# Note: type subtypes (book, person, recipe, etc.) live in type-dictionary.md — not here.

## Tags

loci
requirements
design
pkm
knowledge-graph
architecture
"""

FOREIGN_DEFINITIONS = """\
# Loci Foreign Definitions
# Metadata schemas for external content sources.
# Added automatically by the save skill on first encounter with a new source.

# Example entry:
# source_type: jira_ticket
# fields:
#   - title
#   - status
#   - assignee
#   - description
#   - url
#   - priority
# last_updated: 2026-03-21
"""


def load_config() -> Optional[dict]:
    """Load existing config if present."""
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
    """Create vault folder structure and seed meta files."""
    vault_root.mkdir(parents=True, exist_ok=True)

    for folder in VAULT_FOLDERS:
        folder_path = vault_root / folder
        folder_path.mkdir(exist_ok=True)
        print(f"  Created: {folder_path}")

    # Seed meta files if they don't exist
    type_dict_path = vault_root / "meta" / "type-dictionary.md"
    if not type_dict_path.exists():
        type_dict_path.write_text(TYPE_DICTIONARY)
        print(f"  Seeded: {type_dict_path}")

    tag_dict_path = vault_root / "meta" / "tag-dictionary.md"
    if not tag_dict_path.exists():
        tag_dict_path.write_text(TAG_DICTIONARY)
        print(f"  Seeded: {tag_dict_path}")

    foreign_defs_path = vault_root / "meta" / "foreign-definitions.md"
    if not foreign_defs_path.exists():
        foreign_defs_path.write_text(FOREIGN_DEFINITIONS)
        print(f"  Seeded: {foreign_defs_path}")


def setup_interactive() -> dict:
    """Interactive first-run setup flow."""
    print("\nLoci is not configured yet. Let's set it up.\n")

    # Nextcloud location
    default_nc = Path.home() / "Nextcloud"
    nc_input = input(f"Where is your Nextcloud folder? (default: {default_nc}): ").strip()
    nextcloud_root = Path(nc_input) if nc_input else default_nc

    if not nextcloud_root.exists():
        print(f"Warning: {nextcloud_root} does not exist. Creating it.")
        nextcloud_root.mkdir(parents=True)

    # Vault folder name
    vault_name = input("Vault folder name inside Nextcloud (default: loci): ").strip()
    if not vault_name:
        vault_name = "loci"

    vault_root = nextcloud_root / vault_name

    config = {
        "vault_root": str(vault_root),
        "webdav_url": None,  # TBD when MCP layer is built
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
    }

    return config


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

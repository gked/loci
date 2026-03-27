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

TYPE_DICTIONARY = """\
# Loci Type Dictionary
# Canonical type vocabulary — edit with care.
# The save skill reads this file at runtime.

document     — written content that doesn't fit a more specific type: essays, specs, design docs, meeting notes, journal entries, longform notes; the default fallback type
article      — external content consumed and captured (format carried by tag: #book, #article, #paper, #video)
bookmark     — saved URL with light metadata only; use article when capturing full content
conversation — saved LLM or human conversation (has turns, participants, model/person)
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, organization, or place (subtype field: person | organization | place)
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

RELATION_DICTIONARY = """\
# Loci Relation Dictionary
# Canonical vocabulary for typed edges between vault nodes.
# The save skill reads this file at runtime when suggesting relation types.
# Use the most specific type that fits. Fall back to relates-to only when nothing else applies.
# Format: type — definition

## Structural / Ownership

belongs-to    — this item is owned by or lives inside a larger whole (task→project, note→topic)
is-part-of    — this item is a structural sub-component of another (chapter inside a book, section inside a document); prefer over belongs-to for content hierarchy
has-part      — inverse of is-part-of; the current node contains the linked node as a component

## Provenance / Derivation

is-based-on   — this item was derived from or builds directly on another (a note summarising an article; a draft based on a source)
same-work-as  — both nodes are different manifestations of the same underlying work (preprint + published version, original + translation)
supersedes    — this item replaces or updates an older node; the older node remains but is deprecated
version-of    — this item is a revision or variant of another without fully replacing it

## Semantic

about         — this node is primarily about another node (especially: article or note → topic node)
mentions      — this node references another in passing, without being primarily about it; lighter than about
influences    — one node shapes, informs, or has affected the direction of another
supports      — provides evidence, reasoning, or examples for a claim in another node
contradicts   — challenges, refutes, or conflicts with the content of another node
inspired-by   — conceptually sparked by another node, but not a direct derivation

## Generic

relates-to    — unspecified bidirectional connection; use only when no other type fits
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

    relation_dict_path = vault_root / "meta" / "relation-dictionary.md"
    if not relation_dict_path.exists():
        relation_dict_path.write_text(RELATION_DICTIONARY)
        print(f"  Seeded: {relation_dict_path}")


def setup_interactive() -> dict:
    """Interactive first-run setup flow."""
    print("\nLoci is not configured yet. Let's set it up.\n")

    default_vault = Path(__file__).parent.parent / "vault"
    vault_input = input(f"Where should the vault live? (default: {default_vault}): ").strip()
    vault_root = Path(vault_input) if vault_input else default_vault

    default_remote = ""
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

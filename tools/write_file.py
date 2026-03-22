"""
write_file.py
Writes a Locus vault item to the filesystem.

Handles:
- Frontmatter serialization
- File path resolution from config
- Duplicate detection
- Directory creation if missing
"""

import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

# Import sibling tools
sys.path.insert(0, str(Path(__file__).parent))
from uid_generator import generate_uid
from slug import filename as make_filename
from vault_init import load_config


TYPE_FOLDERS = {
    "note": "notes",
    "article": "articles",
    "conversation": "conversations",
    "project": "projects",
    "task": "tasks",
    "event": "events",
    "entity": "entities",
    "procedure": "procedures",
    "topic": "topics",
    "reference": "references",
}


def serialize_frontmatter(fields: dict) -> str:
    """Serialize a dict to YAML frontmatter block."""
    return "---\n" + yaml.dump(fields, default_flow_style=False, allow_unicode=True) + "---\n"


def resolve_vault_root() -> Path:
    """Load vault root from config."""
    config = load_config()
    if not config:
        raise RuntimeError(
            "Locus is not configured. Run: python tools/vault_init.py"
        )
    return Path(config["vault_root"])


def check_duplicate(vault_root: Path, type_folder: str, title: str, url: str = None) -> Path | None:
    """
    Check for likely duplicate items in the type folder.
    Returns the path of a likely duplicate, or None.
    """
    folder = vault_root / type_folder
    if not folder.exists():
        return None

    title_lower = title.lower()

    for existing_file in folder.glob("*.md"):
        # Check title similarity via filename slug
        if title_lower.replace(" ", "-") in existing_file.stem:
            return existing_file

        # Check URL match in file content if URL provided
        if url:
            content = existing_file.read_text()
            if url in content:
                return existing_file

    return None


def write_item(
    type: str,
    title: str,
    body: str,
    tags: list = None,
    domains: list = None,
    summary: str = None,
    author: str = "self",
    relations: list = None,
    references: list = None,
    extra_fields: dict = None,
    date: str = None,
    skip_duplicate_check: bool = False,
) -> dict:
    """
    Write a Locus vault item to the filesystem.

    Args:
        type: One of the canonical Locus types
        title: Item title
        body: Main content body (markdown)
        tags: List of freeform tags
        domains: List of domain taxonomy values
        summary: One-paragraph summary
        author: Author identifier (default: "self")
        relations: List of {uid, type} dicts
        references: List of {url, title, source_type} dicts
        extra_fields: Type-specific frontmatter fields
        date: Override date string YYYY-MM-DD (default: today)
        skip_duplicate_check: Skip duplicate detection

    Returns:
        Dict with saved item metadata: uid, path, type, title
    """
    if type not in TYPE_FOLDERS:
        raise ValueError(f"Unknown type '{type}'. Must be one of: {list(TYPE_FOLDERS.keys())}")

    vault_root = resolve_vault_root()
    type_folder = TYPE_FOLDERS[type]
    folder_path = vault_root / type_folder
    folder_path.mkdir(parents=True, exist_ok=True)

    # Date
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Duplicate check
    if not skip_duplicate_check:
        url = None
        if references:
            url = references[0].get("url")
        duplicate = check_duplicate(vault_root, type_folder, title, url)
        if duplicate:
            print(f"\nWarning: A similar item already exists: {duplicate.name}")
            print("Save as new item anyway? (y/n): ", end="")
            answer = input().strip().lower()
            if answer != "y":
                print("Aborted.")
                return {}

    # Generate UID and filename
    uid = generate_uid()
    fname = make_filename(title, date)
    file_path = folder_path / fname

    # Build frontmatter
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = {
        "uid": uid,
        "type": type,
        "title": title,
        "author": author,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
        "tags": tags or [],
        "domains": domains or [],
        "summary": summary,
        "relations": relations or [],
        "references": references or [],
    }

    # Merge type-specific fields
    if extra_fields:
        frontmatter.update(extra_fields)

    # Write file
    content = serialize_frontmatter(frontmatter) + "\n" + body

    file_path.write_text(content, encoding="utf-8")

    result = {
        "uid": uid,
        "path": str(file_path),
        "type": type,
        "title": title,
    }

    print(f"\nSaved: {file_path}")
    print(f"UID:   {uid}")
    print(f"Type:  {type}")
    print(f"Links: {len(relations or [])}")

    return result


if __name__ == "__main__":
    # Quick smoke test
    result = write_item(
        type="note",
        title="Test Note from write_file",
        body="This is a test note written by write_file.py.",
        tags=["test", "smoke-test"],
        domains=["technology-engineering"],
        summary="A quick smoke test to verify write_file.py works correctly.",
    )
    print("\nResult:", result)

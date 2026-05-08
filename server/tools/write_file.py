"""
write_file.py
Writes a Loci vault item to the filesystem.

Handles:
- Frontmatter serialization
- File path resolution from config
- Duplicate detection
- Directory creation if missing

Concurrency note: write_item and patch_item perform read-modify-write
operations without file locking. Running both the local stdio MCP server
and the Docker SSE server against the same vault simultaneously is supported
for typical personal use, but simultaneous writes to the *same file* from
two clients can produce a torn write. If you need stricter consistency,
add your own file locking (e.g. fcntl.flock) around the write path.
"""

import sys
import yaml
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

# Import sibling tools
sys.path.insert(0, str(Path(__file__).parent))
from uid_generator import generate_uid
from slug import filename as make_filename
from vault_init import load_config
from type_registry import get_registry
from relation_registry import get_relation_registry


def serialize_frontmatter(fields: dict) -> str:
    """Serialize a dict to YAML frontmatter block."""
    return "---\n" + yaml.dump(fields, default_flow_style=False, allow_unicode=True) + "---\n"


def resolve_vault_root() -> Path:
    """Load vault root from config."""
    config = load_config()
    if not config:
        raise RuntimeError(
            "Loci is not configured. Run: python tools/vault_init.py"
        )
    return Path(config["vault_root"])


def check_duplicate(vault_root: Path, title: str, url: str = None) -> Optional[Path]:
    """
    Check for likely duplicate items in the vault root.
    Returns the path of a likely duplicate, or None.
    """
    title_lower = title.lower()

    for existing_file in vault_root.glob("*.md"):
        # Check title similarity via filename slug
        if title_lower.replace(" ", "-") in existing_file.stem:
            return existing_file

        # Check URL match in file content if URL provided
        if url:
            content = existing_file.read_text()
            if url in content:
                return existing_file

    return None


def validate_required_fields(type_def, extra_fields: dict) -> list[str]:
    """
    Validate type-specific required fields and enum constraints.

    Checks that every required field for the type is present and non-null in
    extra_fields, and that enum fields contain only valid values.

    Args:
        type_def: TypeDef from the registry
        extra_fields: Type-specific frontmatter fields provided by the caller

    Returns:
        List of error strings; empty list means valid.
    """
    ef = extra_fields or {}
    errors: list[str] = []

    for field_name in type_def.required_names():
        if field_name not in ef or ef[field_name] is None:
            errors.append(f"Required field '{field_name}' is missing or null for type '{type_def.name}'")

    for field_name, valid_values in type_def.enum_constraints().items():
        if field_name in ef and ef[field_name] is not None:
            if ef[field_name] not in valid_values:
                errors.append(
                    f"Invalid value '{ef[field_name]}' for field '{field_name}'. "
                    f"Must be one of: {sorted(valid_values)}"
                )

    return errors


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
    skip_duplicate_check: bool = False,
) -> dict:
    """
    Write a Loci vault item to the filesystem.

    Args:
        type: One of the canonical Loci types
        title: Item title
        body: Main content body (markdown)
        tags: List of freeform tags
        domains: List of domain taxonomy values
        summary: One-paragraph summary
        author: Author identifier (default: "self")
        relations: List of {uid, type} dicts
        references: List of {url, title, source_type} dicts
        extra_fields: Type-specific frontmatter fields
        skip_duplicate_check: Skip duplicate detection

    Returns:
        Dict with saved item metadata: uid, path, type, title.
        Returns {"errors": [...]} if required field validation fails.
    """
    vault_root = resolve_vault_root()
    registry = get_registry(vault_root)
    if type not in registry.type_names():
        raise ValueError(
            f"Unknown type '{type}'. Must be one of: {sorted(registry.type_names())}"
        )

    type_def = registry.get(type)
    validation_errors = validate_required_fields(type_def, extra_fields)
    if validation_errors:
        return {"errors": validation_errors}

    relation_registry = get_relation_registry(vault_root)
    relation_errors = []
    for rel in (relations or []):
        rel_type = rel.get("type")
        if rel_type and not relation_registry.is_valid(rel_type):
            relation_errors.append(
                f"Unknown relation type '{rel_type}'. "
                f"Call read_meta(file='relation-dictionary') to see valid types."
            )
    if relation_errors:
        return {"errors": relation_errors}

    vault_root.mkdir(parents=True, exist_ok=True)

    # Duplicate check
    if not skip_duplicate_check:
        url = None
        if references:
            url = references[0].get("url")
        duplicate = check_duplicate(vault_root, title, url)
        if duplicate:
            print(f"\nWarning: A similar item already exists: {duplicate.name}")
            print("Save as new item anyway? (y/n): ", end="")
            answer = input().strip().lower()
            if answer != "y":
                print("Aborted.")
                return {}

    # Generate UID and filename
    uid = generate_uid()
    fname = make_filename(title)
    file_path = vault_root / fname

    # Build frontmatter
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = {
        "uid": uid,
        "type": type,
        "title": title,
        "author": author,
        "state": "active",
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


def patch_item(path: str, updates: dict, body: str = None) -> dict:
    """
    Patch frontmatter fields in an existing vault item.

    Args:
        path: Absolute path to the vault file.
        updates: Frontmatter fields to merge into the existing frontmatter.
                 Pass the complete new value for any field you want to change
                 (e.g. the full new relations list, not just the delta).
        body: If provided, replaces the existing body text.

    Returns:
        Dict with {uid, path, type, title}.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")

    relation_warnings: list[str] = []
    if "relations" in updates:
        vault_root = resolve_vault_root()
        relation_registry = get_relation_registry(vault_root)
        for rel in (updates.get("relations") or []):
            rel_type = rel.get("type")
            if rel_type and not relation_registry.is_valid(rel_type):
                relation_warnings.append(
                    f"Unknown relation type '{rel_type}'. "
                    f"Call read_meta(file='relation-dictionary') to see valid types."
                )

    raw = p.read_text(encoding="utf-8")

    # Split frontmatter from body
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            existing_body = parts[2].lstrip("\n")
        else:
            fm = {}
            existing_body = raw
    else:
        fm = {}
        existing_body = raw

    # Merge updates
    fm.update(updates)
    fm["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # yaml.safe_load converts datetime strings to Python datetime objects; convert
    # them back to strings so yaml.dump preserves the canonical YYYY-MM-DDTHH:MM:SSZ format.
    for key, val in fm.items():
        if isinstance(val, datetime):
            fm[key] = val.strftime("%Y-%m-%dT%H:%M:%SZ")

    final_body = body if body is not None else existing_body
    content = serialize_frontmatter(fm) + "\n" + final_body
    p.write_text(content, encoding="utf-8")

    result = {
        "uid": fm.get("uid"),
        "path": str(p),
        "type": fm.get("type"),
        "title": fm.get("title"),
        "state": fm.get("state", "active"),
        "relations": fm.get("relations") or [],
        "tags": fm.get("tags") or [],
        "domains": fm.get("domains") or [],
        "summary": fm.get("summary", ""),
    }
    if relation_warnings:
        result["relation_warnings"] = relation_warnings
    return result


if __name__ == "__main__":  # pragma: no cover
    # Quick smoke test
    result = write_item(
        type="document",
        title="Test Document from write_file",
        body="This is a test document written by write_file.py.",
        tags=["test", "smoke-test"],
        domains=["technology-engineering"],
        summary="A quick smoke test to verify write_file.py works correctly.",
    )
    print("\nResult:", result)

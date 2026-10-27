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
and the SSE server against the same vault simultaneously is supported
for typical personal use, but simultaneous writes to the *same file* from
two clients can produce a torn write. If you need stricter consistency,
add your own file locking (e.g. fcntl.flock) around the write path.
"""

import re
import sys
import yaml
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

# Import sibling tools
from loci.tools.uid_generator import generate_uid
from loci.tools.slug import filename as make_filename
from loci.tools.vault_init import NON_NODE_DIRS, NOT_CONFIGURED_MESSAGE, load_config
from loci.tools.type_registry import get_registry
from loci.tools.relation_registry import get_relation_registry
from loci.tools.frontmatter import load_frontmatter, split_frontmatter
from loci.tools.tag_hygiene import as_tag_list


def serialize_frontmatter(fields: dict) -> str:
    """Serialize a dict to YAML frontmatter block."""
    return "---\n" + yaml.dump(fields, default_flow_style=False, allow_unicode=True) + "---\n"


def resolve_vault_root() -> Path:
    """Load vault root from config."""
    config = load_config()
    if not config:
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    return Path(config["vault_root"])


def _normalize_title(title: str) -> str:
    return " ".join(str(title).split()).lower()


def _normalize_url(url: str) -> str:
    return str(url).strip().rstrip("/")


def check_duplicate(vault_root: Path, title: str, url: str = None) -> Optional[Path]:
    """
    Check for likely duplicate items in the vault. Returns the path of a
    likely duplicate, or None.

    A duplicate is a node whose title equals this title (case- and
    whitespace-insensitive) or whose `source_url` equals `url` (trailing slash
    ignored). Equality rather than substring on purpose: api.save refuses on a
    hit, and a substring rule made "Test" a duplicate of "Build test suite" and
    a shorter URL a duplicate of any node that merely cited a longer one.

    Titles are not compared by slug: a slug is truncated and stripped of
    punctuation, so two notes that differ only in a date past the cut-off
    would refuse each other. Filename collisions are free_filename's job, not
    this check's.

    Read from disk rather than the graph index: the index only rebuilds when
    a directory mtime moves, and an in-place edit (retitling a note in an
    editor) does not move it, so the index can carry a title that no longer
    exists. A save is not a hot path; a wrong refusal costs more than a scan.
    """
    wanted = _normalize_title(title)
    wanted_url = _normalize_url(url) if url else ""
    if not wanted and not wanted_url:
        return None

    for md_file in vault_root.rglob("*.md"):
        if md_file.parent.name in NON_NODE_DIRS:
            continue
        try:
            fm, _ = load_frontmatter(md_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not fm:
            continue
        if wanted and _normalize_title(fm.get("title") or "") == wanted:
            return md_file
        if wanted_url and _normalize_url(fm.get("source_url") or "") == wanted_url:
            return md_file

    return None


UID_RE = re.compile(r"[0-9a-f]{8}")


def find_uid(vault_root: Path, uid: str) -> Optional[Path]:
    """
    Return the path of the node whose frontmatter carries `uid`, or None.

    Read from disk for the same reason check_duplicate does: the graph index
    can lag an in-place edit, and a save is not a hot path.
    """
    for md_file in vault_root.rglob("*.md"):
        if md_file.parent.name in NON_NODE_DIRS:
            continue
        try:
            fm, _ = load_frontmatter(md_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fm and str(fm.get("uid") or "") == uid:
            return md_file
    return None


def free_filename(vault_root: Path, title: str) -> str:
    """
    Return a filename for `title` that no file in `vault_root` uses yet.

    The name is derived from the title alone, so a second node with the same
    title (allow_duplicate) would otherwise land on the first node's path and
    replace it. Suffix -2, -3, … until the path is free.
    """
    fname = make_filename(title)
    if not (vault_root / fname).exists():
        return fname
    stem, ext = fname.rsplit(".", 1)
    n = 2
    while (vault_root / f"{stem}-{n}.{ext}").exists():
        n += 1
    return f"{stem}-{n}.{ext}"


def validate_required_fields(type_def, extra_fields: dict, subtype: Optional[str] = None) -> list[str]:
    """
    Validate type-specific required fields and enum constraints.

    Checks that every required field for the type is present and non-null in
    extra_fields, and that enum fields contain only valid values.

    Args:
        type_def: TypeDef from the registry
        extra_fields: Type-specific frontmatter fields provided by the caller
        subtype: Subtype value (e.g. 'book' for asset nodes) to include subtype-specific enum constraints

    Returns:
        List of error strings; empty list means valid.
    """
    ef = extra_fields or {}
    errors: list[str] = []

    for field_name in type_def.required_names():
        if field_name not in ef or ef[field_name] is None:
            errors.append(f"Required field '{field_name}' is missing or null for type '{type_def.name}'")

    for field_name, valid_values in type_def.enum_constraints(subtype=subtype).items():
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
        extra_fields: Type-specific frontmatter fields. A 'body' key here is
                      rerouted to the body argument — it is not a frontmatter field.
        skip_duplicate_check: Skip duplicate detection

    Returns:
        Dict with saved item metadata: uid, path, type, title.
        Adds "body_warnings" if a body was found in extra_fields.
        Returns {"errors": [...]} if required field validation fails.
    """
    vault_root = resolve_vault_root()
    registry = get_registry(vault_root)
    if type not in registry.type_names():
        raise ValueError(
            f"Unknown type '{type}'. Must be one of: {sorted(registry.type_names())}"
        )

    # 'body' is not a frontmatter field, and no type declares one. Letting it
    # through extra_fields serialises the whole body as a quoted YAML scalar,
    # and a '---' line inside it stops the node parsing — the same corruption
    # patch_item guards against. Reroute it here too rather than write it.
    body_warnings: list[str] = []
    extra_fields = dict(extra_fields or {})
    if "body" in extra_fields:
        misrouted = extra_fields.pop("body")
        if body:
            body_warnings.append(
                "'body' was passed inside extra_fields; it is not a frontmatter "
                "field. The body argument won and the extra_fields copy was discarded."
            )
        else:
            body = misrouted or ""
            body_warnings.append(
                "'body' was passed inside extra_fields; treated as the body argument. "
                "Pass body=... directly — it is not a frontmatter field."
            )

    type_def = registry.get(type)
    subtype = (extra_fields or {}).get("subtype")
    validation_errors = validate_required_fields(type_def, extra_fields, subtype=subtype)
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

    # TODO Phase 5: validate has_asset list structure against SchemeRegistry here
    # (block on write for unknown schemes / missing required fields, matching
    # the relation validation pattern above).

    vault_root.mkdir(parents=True, exist_ok=True)

    # A caller that already holds a uid (save_asset, which wrote an intent
    # file under it; a skill that called generate_uid first) passes it in
    # extra_fields. The file always honoured that; the return value and the
    # graph index must too, or the caller is told a uid that exists nowhere.
    # A uid that is already on disk is refused rather than reused: api.save
    # indexes the graph under it, and index_node on an existing uid rewrites
    # that node's attributes and drops its edges.
    # It must also be a uid in the vault's own form — the lookup in api.get
    # and the linter both recognise nothing else, so any other value would be
    # reported back and then be unreachable by it.
    given_uid = (extra_fields or {}).get("uid")
    if given_uid:
        uid = str(given_uid)
        if not UID_RE.fullmatch(uid):
            return {"errors": [
                f"uid '{uid}' is not a valid uid (8 lowercase hex characters). "
                "Omit uid to have one generated, or call generate_uid for a fresh one."
            ]}
        taken = find_uid(vault_root, uid)
        if taken is not None:
            return {"errors": [
                f"uid '{uid}' already belongs to {taken.name}. "
                "Omit uid to have one generated, or call generate_uid for a fresh one."
            ]}
    else:
        uid = generate_uid()

    # Duplicate check
    if not skip_duplicate_check:
        url = (extra_fields or {}).get("source_url")
        duplicate = check_duplicate(vault_root, title, url)
        if duplicate:
            print(f"\nWarning: A similar item already exists: {duplicate.name}")
            print("Save as new item anyway? (y/n): ", end="")
            answer = input().strip().lower()
            if answer != "y":
                print("Aborted.")
                return {}

    fname = free_filename(vault_root, title)
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
        "tags": as_tag_list(tags),
        "domains": domains or [],
        "summary": summary,
        "relations": relations or [],
        "references": references or [],
    }

    # Merge type-specific fields. The uid was resolved above; a None or empty
    # uid in extra_fields must not land in the file over the generated one.
    if extra_fields:
        frontmatter.update(extra_fields)
        frontmatter["uid"] = uid

    # Write file
    content = serialize_frontmatter(frontmatter) + "\n" + body

    file_path.write_text(content, encoding="utf-8")

    result = {
        "uid": uid,
        "path": str(file_path),
        "type": type,
        "title": title,
    }
    if body_warnings:
        result["body_warnings"] = body_warnings

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
                 A 'body' key here is rerouted to the body argument — see below.
        body: If provided, replaces the existing body text.

    Returns:
        Dict with {uid, path, type, title}.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")

    updates = dict(updates or {})
    body_warnings: list[str] = []

    # 'body' is not a frontmatter field. Merging it into the frontmatter dict
    # serialises the whole body as a quoted YAML scalar, and if that body
    # contains a '---' line the node stops parsing entirely. Callers that meant
    # body= get what they meant, with a warning, rather than a corrupted node.
    if "body" in updates:
        misrouted = updates.pop("body")
        if body is not None:
            body_warnings.append(
                "'body' was passed both inside updates and as the body argument; "
                "the body argument won and the updates copy was discarded."
            )
        elif misrouted is None:
            # An explicit null means "empty this body". Falling through to the
            # `body is not None` check below would keep the old body while still
            # reporting the call as applied, so make the clear explicit.
            body = ""
            body_warnings.append(
                "'body' was passed inside updates as null; the body has been cleared. "
                "Pass body='' directly — it is not a frontmatter field."
            )
        else:
            body = misrouted
            body_warnings.append(
                "'body' was passed inside updates; treated as the body argument. "
                "Pass body=... directly — it is not a frontmatter field."
            )

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

    # TODO Phase 5: validate has_asset list structure in updates against SchemeRegistry
    # (warn on patch for unknown schemes / missing required fields).

    raw = p.read_text(encoding="utf-8")

    # Split frontmatter from body
    fm_text, rest = split_frontmatter(raw)
    if fm_text is None:
        fm = {}
        existing_body = raw
    else:
        fm = yaml.safe_load(fm_text) or {}
        existing_body = rest.lstrip("\n")

    # A 'body' key in the frontmatter is always damage from an earlier misrouted
    # call — no type declares one. Strip it on every patch, otherwise the tool
    # that caused the corruption is also the one tool that cannot repair it.
    if "body" in fm:
        fm.pop("body")
        body_warnings.append(
            "Removed a stale 'body' key from this node's frontmatter; "
            "'body' is not a frontmatter field."
        )

    # Merge updates
    fm.update(updates)
    fm["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A scalar `tags: rust` — hand-edited, or passed as a string — is one tag.
    # Persist it as the list every reader expects, so the file is repaired
    # by the next patch rather than read letter by letter forever.
    if "tags" in fm:
        fm["tags"] = as_tag_list(fm["tags"])

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
        "tags": as_tag_list(fm.get("tags")),
        "domains": fm.get("domains") or [],
        "summary": fm.get("summary", ""),
        "source_url": fm.get("source_url") or "",
        "subtype": fm.get("subtype") or "",
        "aliases": fm.get("aliases") or [],
        "language": fm.get("language") or "",
    }
    if relation_warnings:
        result["relation_warnings"] = relation_warnings
    if body_warnings:
        result["body_warnings"] = body_warnings
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

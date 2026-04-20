"""
vault_linter.py
Validates vault files against the Loci schema.

Checks performed:
  Errors:
    - unparseable or missing frontmatter
    - unknown type
    - missing required base fields
    - missing type-specific required fields
    - invalid enum values (status, priority, format, platform, subtype)
    - malformed uid (not 8-char hex)
    - duplicate uids across the vault

  Warnings:
    - dangling relations (uid not found in vault)
    - orphaned nodes (no relations)
    - empty summary

Usage:
    python tools/vault_linter.py [vault_root]

Note: the inline SCHEMA here mirrors the planned ontology.yaml format and
will be replaced by an ontology loader once that file lands.
"""

import re
import sys
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).parent))
from vault_init import load_config
from type_registry import TypeRegistry, get_registry, REFERENCES_DIR

BASE_REQUIRED = [
    "uid", "type", "title", "author",
    "created_at", "updated_at",
    "archived_at",
    "tags", "domains", "summary",
    "relations", "references",
]

UID_RE = re.compile(r"^[0-9a-f]{8}$")


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------

@dataclass
class LintIssue:
    path: str
    severity: Literal["error", "warning"]
    code: str
    message: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Single-file lint
# ---------------------------------------------------------------------------

def lint_file(
    path: Path,
    all_uids: set[str],
    registry: TypeRegistry,
) -> list[LintIssue]:
    """Lint a single vault file against the type registry."""
    issues: list[LintIssue] = []
    name = path.name

    raw = path.read_text(encoding="utf-8")

    if not raw.startswith("---"):
        return [LintIssue(name, "error", "no-frontmatter", "No YAML frontmatter found")]

    parts = raw.split("---", 2)
    if len(parts) < 3:
        return [LintIssue(name, "error", "malformed-frontmatter", "Frontmatter block is not closed")]

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return [LintIssue(name, "error", "invalid-yaml", f"YAML parse error: {exc}")]

    # type — must be present and known before any further checks
    node_type = fm.get("type")
    if not node_type:
        issues.append(LintIssue(name, "error", "missing-type", "Missing required field 'type'"))
        return issues

    type_def = registry.get(node_type)
    if type_def is None:
        issues.append(LintIssue(name, "error", "unknown-type", f"Unknown type '{node_type}'"))
        return issues

    # uid
    uid = fm.get("uid")
    if not uid:
        issues.append(LintIssue(name, "error", "missing-uid", "Missing required field 'uid'"))
    elif not UID_RE.match(str(uid)):
        issues.append(LintIssue(name, "error", "invalid-uid",
            f"'uid' value '{uid}' is not 8-character lowercase hex"))

    # required base fields — presence check only (some fields like archived_at are validly null)
    for f in BASE_REQUIRED:
        if f == "uid":
            continue  # already checked above
        if f not in fm:
            issues.append(LintIssue(name, "error", "missing-field",
                f"Missing required field '{f}'"))

    # type-specific required fields
    for field_def in type_def.required_fields:
        if field_def.name not in fm or fm[field_def.name] is None:
            issues.append(LintIssue(name, "error", "missing-field",
                f"Missing required field '{field_def.name}' for type '{node_type}'"))

    # enum values
    for field_name, valid_values in type_def.enum_constraints().items():
        val = fm.get(field_name)
        if val is not None and str(val) not in valid_values:
            issues.append(LintIssue(name, "error", "invalid-enum",
                f"'{field_name}' value '{val}' is not valid — "
                f"expected one of: {sorted(valid_values)}"))

    # dangling relations
    for rel in (fm.get("relations") or []):
        if not isinstance(rel, dict):
            continue
        rel_uid = rel.get("uid")
        if rel_uid and str(rel_uid) not in all_uids:
            issues.append(LintIssue(name, "warning", "dangling-relation",
                f"Relation uid '{rel_uid}' does not exist in the vault"))

    # orphaned node
    if not (fm.get("relations") or []):
        issues.append(LintIssue(name, "warning", "orphaned-node",
            "Node has no relations — isolated from the graph"))

    # empty summary
    summary = fm.get("summary")
    if not summary or not str(summary).strip():
        issues.append(LintIssue(name, "warning", "empty-summary", "Summary is empty"))

    return issues


# ---------------------------------------------------------------------------
# Vault-wide lint
# ---------------------------------------------------------------------------

def lint_vault(vault_root: Path) -> dict:
    """
    Lint all vault files under vault_root.
    Returns {"errors": [...], "warnings": [...], "stats": {...}}.
    """
    registry = get_registry(vault_root)
    md_files = sorted(f for f in vault_root.glob("*.md"))

    # Pass 1: collect all uids and detect duplicates
    uid_map: dict[str, list[str]] = {}
    for path in md_files:
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        uid = fm.get("uid")
        if uid:
            uid_map.setdefault(str(uid), []).append(path.name)

    all_uids = set(uid_map.keys())

    dup_issues: list[LintIssue] = []
    for uid, files in uid_map.items():
        if len(files) > 1:
            for fname in files:
                dup_issues.append(LintIssue(fname, "error", "duplicate-uid",
                    f"uid '{uid}' is shared with: {[f for f in files if f != fname]}"))

    # Pass 2: lint each file
    all_issues: list[LintIssue] = list(dup_issues)
    for path in md_files:
        all_issues.extend(lint_file(path, all_uids, registry))

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    return {
        "errors": [i.as_dict() for i in errors],
        "warnings": [i.as_dict() for i in warnings],
        "stats": {
            "files_checked": len(md_files),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        config = load_config()
        if not config:
            print("Loci is not configured. Run: python tools/vault_init.py", file=sys.stderr)
            sys.exit(1)
        root = Path(config["vault_root"])

    result = lint_vault(root)
    stats = result["stats"]
    print(f"\nVault: {root}")
    print(f"Files checked: {stats['files_checked']}")
    print(f"Errors:   {stats['error_count']}")
    print(f"Warnings: {stats['warning_count']}\n")

    for issue in result["errors"]:
        print(f"  ERROR   [{issue['code']}] {issue['path']}: {issue['message']}")
    for issue in result["warnings"]:
        print(f"  WARN    [{issue['code']}] {issue['path']}: {issue['message']}")

    sys.exit(1 if result["errors"] else 0)

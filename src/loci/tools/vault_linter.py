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
from loci.tools.vault_init import load_config
from loci.tools.frontmatter import split_frontmatter
from loci.tools.type_registry import TypeRegistry, get_registry, REFERENCES_DIR
from loci.tools.relation_registry import RelationRegistry, get_relation_registry
from loci.tools.scheme_registry import SchemeRegistry, get_scheme_registry

BASE_REQUIRED = [
    "uid", "type", "title", "author",
    "state",
    "created_at", "updated_at",
    "archived_at",
    "tags", "domains", "summary",
    "relations", "references",
]

# TODO: derive BASE_STATE_VALUES from ontology.yaml once the loader supports enum extraction
BASE_STATE_VALUES = {"active", "archived"}

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
    relation_registry: Optional[RelationRegistry] = None,
    scheme_registry: Optional[SchemeRegistry] = None,
) -> list[LintIssue]:
    """Lint a single vault file against the type registry."""
    issues: list[LintIssue] = []
    name = path.name

    raw = path.read_text(encoding="utf-8")

    if not raw.startswith("---"):
        return [LintIssue(name, "error", "no-frontmatter", "No YAML frontmatter found")]

    fm_text, _ = split_frontmatter(raw)
    if fm_text is None:
        return [LintIssue(name, "error", "malformed-frontmatter", "Frontmatter block is not closed")]

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return [LintIssue(name, "error", "invalid-yaml", f"YAML parse error: {exc}")]
    if not isinstance(fm, dict):
        return [LintIssue(name, "error", "invalid-yaml", "Frontmatter is not a mapping")]

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

    # base state enum check
    state_val = fm.get("state")
    if state_val is not None and state_val not in BASE_STATE_VALUES:
        issues.append(LintIssue(name, "error", "invalid-enum",
            f"'state' value '{state_val}' is not valid — "
            f"expected one of: {sorted(BASE_STATE_VALUES)}"))

    # archived_at consistency: archived nodes should record when they were archived
    if state_val == "archived" and not fm.get("archived_at"):
        issues.append(LintIssue(name, "warning", "missing-archived-at",
            "Node has 'state: archived' but 'archived_at' is not set — "
            "set archived_at to an ISO 8601 timestamp when archiving"))

    # type-specific required fields
    for field_def in type_def.required_fields:
        if field_def.name not in fm or fm[field_def.name] is None:
            issues.append(LintIssue(name, "error", "missing-field",
                f"Missing required field '{field_def.name}' for type '{node_type}'"))

    # enum values (pass subtype so subtype-specific enums like genre:book are checked)
    subtype = fm.get("subtype")
    for field_name, valid_values in type_def.enum_constraints(subtype=subtype).items():
        val = fm.get(field_name)
        if val is not None and str(val) not in valid_values:
            issues.append(LintIssue(name, "error", "invalid-enum",
                f"'{field_name}' value '{val}' is not valid — "
                f"expected one of: {sorted(valid_values)}"))

    # dangling relations and invalid relation types
    for rel in (fm.get("relations") or []):
        if not isinstance(rel, dict):
            continue
        rel_uid = rel.get("uid")
        if rel_uid and str(rel_uid) not in all_uids:
            issues.append(LintIssue(name, "warning", "dangling-relation",
                f"Relation uid '{rel_uid}' does not exist in the vault"))
        rel_type = rel.get("type")
        if rel_type and relation_registry and not relation_registry.is_valid(rel_type):
            issues.append(LintIssue(name, "warning", "invalid-relation-type",
                f"Relation type '{rel_type}' is not in the relation registry"))

    # orphaned node
    if not (fm.get("relations") or []):
        issues.append(LintIssue(name, "warning", "orphaned-node",
            "Node has no relations — isolated from the graph"))

    # empty summary
    summary = fm.get("summary")
    if not summary or not str(summary).strip():
        issues.append(LintIssue(name, "warning", "empty-summary", "Summary is empty"))

    # has_asset structure — only validate when it's the new list form
    has_asset = fm.get("has_asset")
    if has_asset is not None and not isinstance(has_asset, (bool, list)):
        issues.append(LintIssue(name, "warning", "has-asset-unexpected-type",
            f"has_asset should be a list or legacy boolean true (got {type(has_asset).__name__})"))
    if isinstance(has_asset, list):
        for i, variant in enumerate(has_asset):
            if not isinstance(variant, dict):
                issues.append(LintIssue(name, "error", "has-asset-invalid-variant",
                    f"has_asset[{i}] must be a mapping (got {type(variant).__name__})"))
                continue
            if not variant.get("format"):
                issues.append(LintIssue(name, "error", "has-asset-missing-format",
                    f"has_asset[{i}] is missing required 'format' field"))
            locations = variant.get("locations")
            if not locations:
                issues.append(LintIssue(name, "error", "has-asset-missing-locations",
                    f"has_asset[{i}] must have at least one location"))
                continue
            if not isinstance(locations, list):
                issues.append(LintIssue(name, "error", "has-asset-invalid-locations",
                    f"has_asset[{i}].locations must be a list"))
                continue
            for j, loc in enumerate(locations):
                if not isinstance(loc, dict):
                    issues.append(LintIssue(name, "error", "has-asset-invalid-location",
                        f"has_asset[{i}].locations[{j}] must be a mapping"))
                    continue
                scheme = loc.get("scheme")
                if not scheme:
                    issues.append(LintIssue(name, "error", "has-asset-missing-scheme",
                        f"has_asset[{i}].locations[{j}] is missing 'scheme'"))
                    continue
                if scheme_registry and not scheme_registry.is_valid(scheme):
                    issues.append(LintIssue(name, "error", "has-asset-unknown-scheme",
                        f"has_asset[{i}].locations[{j}] uses unknown scheme '{scheme}'"))
                    continue
                if scheme_registry:
                    scheme_def = scheme_registry.get(scheme)
                    for req_field in scheme_def.required_fields:
                        if req_field not in loc:
                            issues.append(LintIssue(name, "error", "has-asset-missing-scheme-field",
                                f"has_asset[{i}].locations[{j}] scheme '{scheme}' "
                                f"requires field '{req_field}'"))

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
    relation_registry = get_relation_registry(vault_root)
    scheme_reg = get_scheme_registry(vault_root)
    md_files = sorted(f for f in vault_root.glob("*.md"))

    # Pass 1: collect all uids and detect duplicates
    uid_map: dict[str, list[str]] = {}
    for path in md_files:
        raw = path.read_text(encoding="utf-8")
        fm_text, _ = split_frontmatter(raw)
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
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
        all_issues.extend(lint_file(path, all_uids, registry, relation_registry, scheme_reg))

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

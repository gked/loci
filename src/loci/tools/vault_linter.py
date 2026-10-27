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
    - a tag that names a project/entity/topic node (should be a relation)
    - a tag that repeats the node's own type or subtype
    - vault-wide: near-duplicate tag spellings (tags used once are reported in
      stats.tags, not as warnings — the long tail is information, not a defect)

Usage:
    python tools/vault_linter.py [vault_root]

Note: the inline SCHEMA here mirrors the planned ontology.yaml format and
will be replaced by an ontology loader once that file lands.
"""

import re
import sys
import yaml
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional
from loci.tools.vault_init import NOT_CONFIGURED_MESSAGE, load_config
from loci.tools.frontmatter import split_frontmatter
from loci.tools.type_registry import TypeRegistry, get_registry, REFERENCES_DIR
from loci.tools.relation_registry import RelationRegistry, get_relation_registry
from loci.tools.scheme_registry import SchemeRegistry, get_scheme_registry, has_asset_issues
from loci.tools import tag_hygiene

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
    for f in registry.base_required:
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

    # has_asset structure — the legacy boolean is accepted, the list form is checked
    for severity, code, message in has_asset_issues(fm.get("has_asset"), scheme_registry):
        issues.append(LintIssue(name, severity, code, message))

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

    # Pass 1: collect all uids and detect duplicates; keep the parsed
    # frontmatter for the tag checks, which need every node's tags and the
    # names of every project/entity/topic before any one file can be judged.
    uid_map: dict[str, list[str]] = {}
    parsed: list[tuple[str, dict]] = []
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
        parsed.append((path.name, fm))
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

    # Pass 3: tags. Per node, a tag that names another node or repeats its
    # own type/subtype. Vault-wide, spellings that collapse into one. Tags
    # used once go into stats only — a small vault is mostly singletons and
    # a warning per tag would drown everything else.
    all_issues.extend(_lint_tags(parsed))
    tag_counts = Counter(t for _, fm in parsed for t in tag_hygiene.as_tag_list(fm.get("tags")))
    near_dupes = tag_hygiene.near_duplicate_groups(tag_counts)
    once = tag_hygiene.singletons(tag_counts)
    for group in near_dupes:
        all_issues.append(LintIssue("(vault)", "warning", "tag-near-duplicate",
            f"tags {group} look like spellings of one tag — if so, keep '{group[0]}' and rename the rest"))

    # Pass 4: the relation vocabulary itself. A relation with no settled
    # reverse cannot be read from the other end of its edge.
    for rel_name, code, message in relation_registry.inverse_problems():
        source = "relation-dictionary.yaml" if relation_registry.is_canonical(rel_name) else "relation-dictionary-user.yaml"
        all_issues.append(LintIssue(f"meta/{source}", "warning", code, message))

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    return {
        "errors": [i.as_dict() for i in errors],
        "warnings": [i.as_dict() for i in warnings],
        "stats": {
            "files_checked": len(md_files),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "tags": {
                "distinct": len(tag_counts),
                "uses": sum(tag_counts.values()),
                "singletons": once,
                "near_duplicates": near_dupes,
            },
        },
    }


def _lint_tags(parsed: list[tuple[str, dict]]) -> list[LintIssue]:
    index = tag_hygiene.build_name_index(fm for _, fm in parsed)
    issues: list[LintIssue] = []
    for name, fm in parsed:
        for w in tag_hygiene.check_tags(
            fm.get("tags"), fm.get("type"), fm.get("subtype"), index,
            self_uid=str(fm.get("uid") or ""), relations=tag_hygiene.list_field(fm, "relations") or [],
        ):
            issues.append(LintIssue(name, "warning", w.code, w.message))
    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        config = load_config()
        if not config:
            print(NOT_CONFIGURED_MESSAGE, file=sys.stderr)
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

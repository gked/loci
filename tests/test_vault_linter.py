"""
tests/test_vault_linter.py
Tests for tools/vault_linter.py: lint_file and lint_vault.
"""

import yaml
import pytest
from pathlib import Path

from loci.tools.vault_linter import lint_file, lint_vault, LintIssue
from loci.tools.type_registry import TypeRegistry, REFERENCES_DIR
from loci.tools.relation_registry import RelationRegistry


@pytest.fixture(scope="module")
def registry():
    return TypeRegistry.load(REFERENCES_DIR / "ontology.yaml")


@pytest.fixture(scope="module")
def relation_registry():
    return RelationRegistry.load(REFERENCES_DIR / "relation-dictionary.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(vault: Path, name: str, fm: dict, body: str = "body") -> Path:
    p = vault / name
    p.write_text(
        "---\n" + yaml.dump(fm, allow_unicode=True) + "---\n\n" + body,
        encoding="utf-8",
    )
    return p


def _valid_task(uid: str = "aabb1122") -> dict:
    return {
        "uid": uid,
        "type": "task",
        "title": "Do something",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": ["test"],
        "domains": ["technology-engineering"],
        "summary": "A test task.",
        "relations": [{"uid": "deadbeef", "type": "belongs-to"}],
        "references": [],
        "status": "todo",
    }


def _valid_log(uid: str = "aabb1122") -> dict:
    return {
        "uid": uid,
        "type": "log",
        "title": "Reading Thinking, Fast and Slow",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": ["reading"],
        "domains": ["psychology"],
        "summary": "Notes from my first read.",
        "relations": [{"uid": "deadbeef", "type": "about"}],
        "references": [],
        "subject_uid": "deadbeef",
        "log_status": "in-progress",
    }


def _valid_asset(uid: str = "aabb1122", subtype: str = "book") -> dict:
    return {
        "uid": uid,
        "type": "asset",
        "title": "Test Book",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": ["book"],
        "domains": ["technology-engineering"],
        "summary": "A test book.",
        "relations": [{"uid": "deadbeef", "type": "belongs-to"}],
        "references": [],
        "subtype": subtype,
    }


def _codes(issues: list[LintIssue]) -> set[str]:
    return {i.code for i in issues}


# ---------------------------------------------------------------------------
# lint_file — frontmatter parsing
# ---------------------------------------------------------------------------

def test_no_frontmatter(tmp_path, registry):
    p = tmp_path / "f.md"
    p.write_text("just some text", encoding="utf-8")
    issues = lint_file(p, set(), registry)
    assert "no-frontmatter" in _codes(issues)


def test_malformed_frontmatter(tmp_path, registry):
    p = tmp_path / "f.md"
    p.write_text("---\nno closing delimiter", encoding="utf-8")
    issues = lint_file(p, set(), registry)
    assert "malformed-frontmatter" in _codes(issues)


def test_invalid_yaml(tmp_path, registry):
    p = tmp_path / "f.md"
    p.write_text("---\n: bad: yaml: [\n---\nbody", encoding="utf-8")
    issues = lint_file(p, set(), registry)
    assert "invalid-yaml" in _codes(issues)


# ---------------------------------------------------------------------------
# lint_file — type checks
# ---------------------------------------------------------------------------

def test_missing_type(tmp_path, registry):
    fm = _valid_task()
    del fm["type"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "missing-type" in _codes(issues)


def test_unknown_type(tmp_path, registry):
    fm = _valid_task()
    fm["type"] = "recipe"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "unknown-type" in _codes(issues)


# ---------------------------------------------------------------------------
# lint_file — uid checks
# ---------------------------------------------------------------------------

def test_missing_uid(tmp_path, registry):
    fm = _valid_task()
    del fm["uid"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"deadbeef"}, registry)
    assert "missing-uid" in _codes(issues)


def test_invalid_uid_too_short(tmp_path, registry):
    fm = _valid_task()
    fm["uid"] = "abc"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"abc", "deadbeef"}, registry)
    assert "invalid-uid" in _codes(issues)


def test_invalid_uid_uppercase(tmp_path, registry):
    fm = _valid_task()
    fm["uid"] = "AABB1122"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"AABB1122", "deadbeef"}, registry)
    assert "invalid-uid" in _codes(issues)


def test_valid_uid_passes(tmp_path, registry):
    fm = _valid_task()
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-uid" not in _codes(issues)
    assert "missing-uid" not in _codes(issues)


# ---------------------------------------------------------------------------
# lint_file — required field checks
# ---------------------------------------------------------------------------

def test_missing_base_field(tmp_path, registry):
    fm = _valid_task()
    del fm["summary"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.code == "missing-field"]
    assert any("summary" in i.message for i in errors)


def test_archived_at_null_is_not_an_error(tmp_path, registry):
    """archived_at: null is valid — presence check only, not value check."""
    fm = _valid_task()
    fm["archived_at"] = None  # explicitly null
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    field_errors = [i for i in issues if i.code == "missing-field" and "archived_at" in i.message]
    assert field_errors == []


def test_missing_type_specific_field(tmp_path, registry):
    fm = _valid_task()
    del fm["status"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.code == "missing-field"]
    assert any("status" in i.message for i in errors)


# ---------------------------------------------------------------------------
# lint_file — enum checks
# ---------------------------------------------------------------------------

def test_invalid_task_status(tmp_path, registry):
    fm = _valid_task()
    fm["status"] = "blocked"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" in _codes(issues)


def test_valid_task_status_duplicate(tmp_path, registry):
    fm = _valid_task()
    fm["status"] = "duplicate"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" not in _codes(issues)


def test_invalid_priority(tmp_path, registry):
    fm = _valid_task()
    fm["priority"] = "critical"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" in _codes(issues)


def test_invalid_entity_subtype(tmp_path, registry):
    fm = {
        "uid": "aabb1122",
        "type": "entity",
        "title": "Someone",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": ["person"],
        "domains": ["technology-engineering"],
        "summary": "An entity.",
        "relations": [{"uid": "deadbeef", "type": "relates-to"}],
        "references": [],
        "subtype": "robot",
    }
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" in _codes(issues)


def test_invalid_book_genre_flagged(tmp_path, registry):
    fm = _valid_asset(subtype="book")
    fm["genre"] = "cooking"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" in _codes(issues)


def test_valid_book_genre_passes(tmp_path, registry):
    fm = _valid_asset(subtype="book")
    fm["genre"] = "technology-computing"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" not in _codes(issues)


def test_genre_not_validated_for_non_book_asset(tmp_path, registry):
    fm = _valid_asset(subtype="video")
    fm["genre"] = "cooking"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" not in _codes(issues)


# ---------------------------------------------------------------------------
# lint_file — relation checks
# ---------------------------------------------------------------------------

def test_dangling_relation(tmp_path, registry):
    fm = _valid_task()
    fm["relations"] = [{"uid": "00000000", "type": "belongs-to"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122"}, registry)  # 00000000 not in vault
    assert "dangling-relation" in _codes(issues)


def test_valid_relation_no_warning(tmp_path, registry):
    fm = _valid_task()
    fm["relations"] = [{"uid": "deadbeef", "type": "belongs-to"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "dangling-relation" not in _codes(issues)


def test_invalid_relation_type_warning(tmp_path, registry, relation_registry):
    fm = _valid_task()
    fm["relations"] = [{"uid": "deadbeef", "type": "invented-type"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry, relation_registry)
    assert "invalid-relation-type" in _codes(issues)


def test_valid_relation_type_no_invalid_warning(tmp_path, registry, relation_registry):
    fm = _valid_task()
    fm["relations"] = [{"uid": "deadbeef", "type": "belongs-to"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry, relation_registry)
    assert "invalid-relation-type" not in _codes(issues)


def test_no_relation_registry_skips_type_check(tmp_path, registry):
    fm = _valid_task()
    fm["relations"] = [{"uid": "deadbeef", "type": "invented-type"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)  # no relation_registry
    assert "invalid-relation-type" not in _codes(issues)


# ---------------------------------------------------------------------------
# lint_file — warnings
# ---------------------------------------------------------------------------

def test_orphaned_node_warning(tmp_path, registry):
    fm = _valid_task()
    fm["relations"] = []
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122"}, registry)
    assert "orphaned-node" in _codes(issues)


def test_empty_summary_warning(tmp_path, registry):
    fm = _valid_task()
    fm["summary"] = ""
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "empty-summary" in _codes(issues)


def test_clean_file_no_issues(tmp_path, registry):
    fm = _valid_task()
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.severity == "error"]
    assert errors == []


# ---------------------------------------------------------------------------
# lint_vault — vault-wide checks
# ---------------------------------------------------------------------------

def test_lint_vault_detects_duplicate_uid(tmp_path):
    fm = _valid_task("aabb1122")
    _write(tmp_path, "a.md", fm)
    _write(tmp_path, "b.md", fm)
    result = lint_vault(tmp_path)
    assert result["stats"]["error_count"] > 0
    assert any(i["code"] == "duplicate-uid" for i in result["errors"])


def test_lint_vault_clean_vault(tmp_path):
    fm_a = _valid_task("aabb1122")
    fm_b = _valid_task("ccdd3344")
    fm_a["relations"] = [{"uid": "ccdd3344", "type": "belongs-to"}]
    fm_b["relations"] = [{"uid": "aabb1122", "type": "belongs-to"}]
    _write(tmp_path, "a.md", fm_a)
    _write(tmp_path, "b.md", fm_b)
    result = lint_vault(tmp_path)
    assert result["stats"]["error_count"] == 0


def test_lint_vault_stats(tmp_path):
    _write(tmp_path, "a.md", _valid_task("aabb1122"))
    _write(tmp_path, "b.md", _valid_task("ccdd3344"))
    result = lint_vault(tmp_path)
    assert result["stats"]["files_checked"] == 2
    assert "error_count" in result["stats"]
    assert "warning_count" in result["stats"]


def test_lint_vault_counts_files_without_frontmatter(tmp_path):
    p = tmp_path / "readme.md"
    p.write_text("# Just a readme\n", encoding="utf-8")
    result = lint_vault(tmp_path)
    assert result["stats"]["files_checked"] == 1
    assert any(i["code"] == "no-frontmatter" for i in result["errors"])


# ---------------------------------------------------------------------------
# lint_file — state field checks
# ---------------------------------------------------------------------------

def test_missing_state_field(tmp_path, registry):
    fm = _valid_task()
    del fm["state"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.code == "missing-field"]
    assert any("state" in i.message for i in errors)


def test_valid_state_active(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "active"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert not any(i.code == "invalid-enum" and "state" in i.message for i in issues)


def test_valid_state_archived(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "archived"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert not any(i.code == "invalid-enum" and "state" in i.message for i in issues)


def test_invalid_state_value(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "deleted"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert any(i.code == "invalid-enum" and "state" in i.message for i in issues)


def test_archived_without_archived_at_warns(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "archived"
    fm["archived_at"] = None
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert any(i.code == "missing-archived-at" for i in issues)


def test_archived_with_archived_at_no_warn(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "archived"
    fm["archived_at"] = "2026-01-01T00:00:00Z"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert not any(i.code == "missing-archived-at" for i in issues)


def test_active_state_no_archived_at_warn(tmp_path, registry):
    fm = _valid_task()
    fm["state"] = "active"
    fm["archived_at"] = None
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert not any(i.code == "missing-archived-at" for i in issues)


# ---------------------------------------------------------------------------
# lint_file — log type
# ---------------------------------------------------------------------------

def test_valid_log_passes(tmp_path, registry):
    p = _write(tmp_path, "log.md", _valid_log())
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "missing-field" not in _codes(issues)


def test_log_missing_subject_uid(tmp_path, registry):
    fm = _valid_log()
    del fm["subject_uid"]
    p = _write(tmp_path, "log.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.code == "missing-field"]
    assert any("subject_uid" in i.message for i in errors)


def test_log_missing_log_status(tmp_path, registry):
    fm = _valid_log()
    del fm["log_status"]
    p = _write(tmp_path, "log.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    errors = [i for i in issues if i.code == "missing-field"]
    assert any("log_status" in i.message for i in errors)


def test_log_invalid_log_status(tmp_path, registry):
    fm = _valid_log()
    fm["log_status"] = "done"
    p = _write(tmp_path, "log.md", fm)
    issues = lint_file(p, {"aabb1122", "deadbeef"}, registry)
    assert "invalid-enum" in _codes(issues)

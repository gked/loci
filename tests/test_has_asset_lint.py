"""
tests/test_has_asset_lint.py
Tests for has_asset structure validation in vault_linter.lint_file.
"""

import yaml
import pytest
from pathlib import Path

from loci.tools.vault_linter import lint_file, LintIssue
from loci.tools.type_registry import TypeRegistry, REFERENCES_DIR
from loci.tools.relation_registry import RelationRegistry
from loci.tools.scheme_registry import SchemeRegistry, reset_scheme_registry


@pytest.fixture(scope="module")
def registry():
    return TypeRegistry.load(REFERENCES_DIR / "ontology.yaml")


@pytest.fixture(scope="module")
def relation_registry():
    return RelationRegistry.load(REFERENCES_DIR / "relation-dictionary.yaml")


@pytest.fixture(scope="module")
def scheme_reg():
    return SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml")


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_scheme_registry()
    yield
    reset_scheme_registry()


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


def _base_doc(uid: str = "aabb1122") -> dict:
    return {
        "uid": uid,
        "type": "document",
        "title": "Test Doc",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": ["test"],
        "domains": ["technology-engineering"],
        "summary": "A test document.",
        "relations": [{"uid": "deadbeef", "type": "belongs-to"}],
        "references": [],
        "status": "draft",
    }


def _codes(issues: list) -> set:
    return {i.code for i in issues}


ALL_UIDS = {"aabb1122", "deadbeef"}


# ---------------------------------------------------------------------------
# has_asset absent — no structural issues
# ---------------------------------------------------------------------------

def test_no_has_asset_passes(tmp_path, registry, relation_registry, scheme_reg):
    p = _write(tmp_path, "f.md", _base_doc())
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-format" not in _codes(issues)
    assert "has-asset-missing-locations" not in _codes(issues)


# ---------------------------------------------------------------------------
# Legacy boolean form — not validated as a list
# ---------------------------------------------------------------------------

def test_legacy_boolean_true_skipped(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = True
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    has_asset_codes = {c for c in _codes(issues) if c.startswith("has-asset")}
    assert has_asset_codes == set()


# ---------------------------------------------------------------------------
# Unexpected type (not bool, not list)
# ---------------------------------------------------------------------------

def test_unexpected_type_string_warns(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = "pdf"
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-unexpected-type" in _codes(issues)


def test_unexpected_type_dict_warns(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = {"format": "pdf"}
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-unexpected-type" in _codes(issues)


# ---------------------------------------------------------------------------
# Valid has_asset list — no errors
# ---------------------------------------------------------------------------

def test_valid_has_asset_list(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [
        {
            "format": "pdf",
            "primary": True,
            "locations": [{"scheme": "local", "path": "assets/aabb1122.pdf"}],
        }
    ]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    has_asset_errs = [i for i in issues if i.code.startswith("has-asset") and i.severity == "error"]
    assert has_asset_errs == []


def test_valid_multi_variant_multi_location(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [
        {
            "format": "pdf",
            "locations": [
                {"scheme": "local", "path": "assets/x.pdf", "priority": 1},
                {"scheme": "s3", "bucket": "my-bucket", "key": "x.pdf", "priority": 2},
            ],
        },
        {
            "format": "html",
            "locations": [{"scheme": "google-drive", "file_id": "abc123"}],
        },
    ]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    errs = [i for i in issues if i.code.startswith("has-asset") and i.severity == "error"]
    assert errs == []


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------

def test_variant_missing_format(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"locations": [{"scheme": "local", "path": "assets/x.pdf"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-format" in _codes(issues)


def test_variant_missing_locations(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-locations" in _codes(issues)


def test_variant_empty_locations(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": []}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-locations" in _codes(issues)


def test_location_missing_scheme(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": [{"path": "assets/x.pdf"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-scheme" in _codes(issues)


def test_location_unknown_scheme(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": [{"scheme": "ftp", "path": "x.pdf"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-unknown-scheme" in _codes(issues)


def test_location_missing_required_scheme_field_local(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": [{"scheme": "local"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-scheme-field" in _codes(issues)


def test_location_missing_required_scheme_field_s3(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": [{"scheme": "s3", "bucket": "my-bucket"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-missing-scheme-field" in _codes(issues)


def test_location_missing_required_scheme_field_gmail(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "eml", "locations": [{"scheme": "gmail", "thread_id": "t1"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    # gmail requires both thread_id and message_id
    assert "has-asset-missing-scheme-field" in _codes(issues)


def test_variant_not_a_dict(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = ["not-a-dict"]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-invalid-variant" in _codes(issues)


def test_locations_not_a_list(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": "assets/x.pdf"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-invalid-locations" in _codes(issues)


def test_location_not_a_dict(tmp_path, registry, relation_registry, scheme_reg):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf", "locations": ["not-a-dict"]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_reg)
    assert "has-asset-invalid-location" in _codes(issues)


# ---------------------------------------------------------------------------
# Validation without scheme_registry — structural checks still run
# ---------------------------------------------------------------------------

def test_format_missing_without_scheme_registry(tmp_path, registry, relation_registry):
    fm = _base_doc()
    fm["has_asset"] = [{"locations": [{"scheme": "local", "path": "assets/x.pdf"}]}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_registry=None)
    assert "has-asset-missing-format" in _codes(issues)


def test_locations_missing_without_scheme_registry(tmp_path, registry, relation_registry):
    fm = _base_doc()
    fm["has_asset"] = [{"format": "pdf"}]
    p = _write(tmp_path, "f.md", fm)
    issues = lint_file(p, ALL_UIDS, registry, relation_registry, scheme_registry=None)
    assert "has-asset-missing-locations" in _codes(issues)


# ---------------------------------------------------------------------------
# find_nodes has_asset filtering
# ---------------------------------------------------------------------------

def test_find_nodes_has_asset_filter(tmp_vault):
    """Integration smoke test: find_nodes(has_asset=True) returns nodes with has_asset."""
    from loci.tools import nx_graph as graph

    doc_with = {
        "uid": "aa000001",
        "type": "document",
        "title": "With Asset",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": [],
        "domains": ["technology-engineering"],
        "summary": "has asset",
        "relations": [],
        "references": [],
        "status": "draft",
        "has_asset": [
            {"format": "pdf", "locations": [{"scheme": "local", "path": "assets/aa000001.pdf"}]}
        ],
    }
    doc_without = {
        "uid": "aa000002",
        "type": "document",
        "title": "Without Asset",
        "author": "self",
        "state": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "archived_at": None,
        "tags": [],
        "domains": ["technology-engineering"],
        "summary": "no asset",
        "relations": [],
        "references": [],
        "status": "draft",
    }

    for fm in (doc_with, doc_without):
        p = tmp_vault / f"{fm['uid']}.md"
        p.write_text("---\n" + yaml.dump(fm, allow_unicode=True) + "---\n\nbody",
                     encoding="utf-8")

    graph.get(tmp_vault)

    with_asset = graph.find(has_asset=True)
    without_asset = graph.find(has_asset=False)
    by_scheme = graph.find(has_asset_scheme="local")
    by_scheme_upper = graph.find(has_asset_scheme="LOCAL")  # case-insensitive

    assert any(n["uid"] == "aa000001" for n in with_asset)
    assert not any(n["uid"] == "aa000002" for n in with_asset)

    assert any(n["uid"] == "aa000002" for n in without_asset)
    assert not any(n["uid"] == "aa000001" for n in without_asset)

    assert any(n["uid"] == "aa000001" for n in by_scheme)
    assert not any(n["uid"] == "aa000002" for n in by_scheme)

    assert any(n["uid"] == "aa000001" for n in by_scheme_upper)

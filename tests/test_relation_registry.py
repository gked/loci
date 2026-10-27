"""
tests/test_relation_registry.py
Tests for tools/relation_registry.py: RelationRegistry class and singleton.
"""

import pytest
from pathlib import Path
from loci.tools.relation_registry import (
    RelationRegistry,
    get_relation_registry,
    reset_relation_registry,
    REFERENCES_DIR,
)


CANONICAL_PATH = REFERENCES_DIR / "relation-dictionary.yaml"

CANONICAL_COUNT = 41


@pytest.fixture(autouse=True)
def clean_registry():
    reset_relation_registry()
    yield
    reset_relation_registry()


# ---------------------------------------------------------------------------
# RelationRegistry.load — canonical only
# ---------------------------------------------------------------------------

def test_loads_all_canonical_relations():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert len(reg.relation_names()) == CANONICAL_COUNT


def test_known_relations_are_valid():
    reg = RelationRegistry.load(CANONICAL_PATH)
    for name in ("belongs-to", "relates-to", "depends-on", "implements", "about"):
        assert reg.is_valid(name), f"Expected '{name}' to be valid"


def test_unknown_relation_is_not_valid():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert not reg.is_valid("assigned-to")
    assert not reg.is_valid("bogus-type")


def test_get_returns_relation_def():
    reg = RelationRegistry.load(CANONICAL_PATH)
    rd = reg.get("depends-on")
    assert rd is not None
    assert rd.name == "depends-on"
    assert rd.group == "dependency-sequencing"
    assert rd.inverse_of == "enables"


def test_get_returns_none_for_unknown():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert reg.get("nonexistent") is None


def test_canonical_relations_are_canonical():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert reg.is_canonical("belongs-to")
    assert reg.is_canonical("relates-to")
    assert reg.is_canonical("implements")


def test_no_warnings_for_clean_canonical():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert reg.warnings == []


# ---------------------------------------------------------------------------
# RelationRegistry.load — user extensions
# ---------------------------------------------------------------------------

def test_user_relation_accepted(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "relations:\n  - name: assigned-to\n    group: entity\n    description: Assigned to a person.\n",
        encoding="utf-8",
    )
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert reg.is_valid("assigned-to")
    assert reg.warnings == []


def test_user_relation_is_not_canonical(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "relations:\n  - name: assigned-to\n    group: entity\n    description: Assigned.\n",
        encoding="utf-8",
    )
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert not reg.is_canonical("assigned-to")
    assert reg.is_valid("assigned-to")


def test_user_relation_collision_skipped_with_warning(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "relations:\n  - name: belongs-to\n    group: structural-ownership\n    description: Collision.\n",
        encoding="utf-8",
    )
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert len(reg.warnings) == 1
    assert "belongs-to" in reg.warnings[0]
    assert reg.is_canonical("belongs-to")


def test_user_relation_missing_name_skipped_with_warning(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "relations:\n  - group: generic\n    description: No name.\n",
        encoding="utf-8",
    )
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert len(reg.warnings) == 1
    assert "missing" in reg.warnings[0].lower()


def test_user_file_not_found_is_ignored(tmp_path):
    reg = RelationRegistry.load(CANONICAL_PATH, tmp_path / "nonexistent.yaml")
    assert len(reg.relation_names()) == CANONICAL_COUNT
    assert reg.warnings == []


def test_empty_user_file(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("relations: []\n", encoding="utf-8")
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert len(reg.relation_names()) == CANONICAL_COUNT
    assert reg.warnings == []


def test_user_extends_total_count(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(
        "relations:\n  - name: assigned-to\n    group: entity\n    description: Assigned.\n",
        encoding="utf-8",
    )
    reg = RelationRegistry.load(CANONICAL_PATH, user_yaml)
    assert len(reg.relation_names()) == CANONICAL_COUNT + 1


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def test_singleton_returns_same_instance():
    r1 = get_relation_registry()
    r2 = get_relation_registry()
    assert r1 is r2


def test_reset_forces_reload():
    r1 = get_relation_registry()
    reset_relation_registry()
    r2 = get_relation_registry()
    assert r1 is not r2


def test_singleton_with_vault_root_no_meta(tmp_path):
    # No meta/ dir → falls back to references
    reg = get_relation_registry(tmp_path)
    assert reg.is_valid("relates-to")
    assert len(reg.relation_names()) == CANONICAL_COUNT


# ---------------------------------------------------------------------------
# Inverses — every relation settles its reverse reading
# ---------------------------------------------------------------------------

def test_every_canonical_relation_names_an_inverse_or_is_symmetric():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert reg.inverse_problems() == []


def test_reverse_of_reads_the_declared_inverse():
    reg = RelationRegistry.load(CANONICAL_PATH)
    assert reg.reverse_of("supersedes") == "superseded-by"
    assert reg.reverse_of("superseded-by") == "supersedes"
    assert reg.reverse_of("works-at") == "employs"


def test_reverse_of_a_symmetric_relation_is_itself():
    reg = RelationRegistry.load(CANONICAL_PATH)
    for name in ("relates-to", "same-work-as", "contradicts"):
        assert reg.reverse_of(name) == name


def test_reverse_of_an_unknown_relation_is_none():
    assert RelationRegistry.load(CANONICAL_PATH).reverse_of("no-such-relation") is None


def _user_registry(tmp_path, body: str) -> RelationRegistry:
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("relations:\n" + body, encoding="utf-8")
    return RelationRegistry.load(CANONICAL_PATH, user_yaml)


def test_a_user_relation_with_neither_inverse_nor_symmetric_is_reported(tmp_path):
    reg = _user_registry(tmp_path, "  - name: assigned-to\n    description: x\n")
    assert [(n, c) for n, c, _ in reg.inverse_problems()] == [("assigned-to", "relation-no-inverse")]


def test_a_symmetric_user_relation_is_not_reported(tmp_path):
    reg = _user_registry(tmp_path, "  - name: friends-with\n    description: x\n    symmetric: true\n")
    assert reg.inverse_problems() == []


def test_an_inverse_that_does_not_name_back_is_reported(tmp_path):
    reg = _user_registry(tmp_path, "  - name: blocks\n    description: x\n    inverse_of: depends-on\n")
    codes = {(n, c) for n, c, _ in reg.inverse_problems()}
    assert ("blocks", "relation-inverse-asymmetric") in codes


def test_an_inverse_naming_an_undefined_relation_is_reported(tmp_path):
    reg = _user_registry(tmp_path, "  - name: blocks\n    description: x\n    inverse_of: nothing\n")
    codes = {(n, c) for n, c, _ in reg.inverse_problems()}
    assert ("blocks", "relation-inverse-unknown") in codes

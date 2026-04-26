"""
tests/test_define_relation.py
Tests for api.define_relation — validate + write to relation-dictionary-user.yaml.
"""

import shutil
import yaml
import pytest
from pathlib import Path

from type_registry import reset_registry
from relation_registry import reset_relation_registry, REFERENCES_DIR


@pytest.fixture(autouse=True)
def clean_registries():
    reset_registry()
    reset_relation_registry()
    yield
    reset_registry()
    reset_relation_registry()


@pytest.fixture
def vault_with_meta(tmp_path):
    """Minimal vault with a seeded meta/ directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    meta = vault / "meta"
    meta.mkdir()
    shutil.copy(REFERENCES_DIR / "relation-dictionary.yaml", meta / "relation-dictionary.yaml")
    shutil.copy(
        REFERENCES_DIR / "relation-dictionary-user.yaml",
        meta / "relation-dictionary-user.yaml",
    )
    import os
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    yield vault
    del os.environ["LOCI_VAULT_ROOT"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_define_relation_minimal(vault_with_meta):
    import api
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
    )
    assert result["defined"] is True
    assert result["name"] == "assigned-to"
    assert result["warnings"] == []

    raw = yaml.safe_load((vault_with_meta / "meta" / "relation-dictionary-user.yaml").read_text())
    assert any(r["name"] == "assigned-to" for r in raw["relations"])


def test_define_relation_with_group(vault_with_meta):
    import api
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
        group="entity",
    )
    assert result["defined"] is True

    raw = yaml.safe_load((vault_with_meta / "meta" / "relation-dictionary-user.yaml").read_text())
    entry = next(r for r in raw["relations"] if r["name"] == "assigned-to")
    assert entry["group"] == "entity"


def test_define_relation_with_inverse_of_known(vault_with_meta):
    """inverse_of pointing to an existing canonical relation — no warning."""
    import api
    # "relates-to" is a canonical relation with no inverse_of — using it is valid
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
        inverse_of="relates-to",
    )
    assert result["defined"] is True
    # "relates-to" has no inverse_of, so no asymmetry warning
    assert result["warnings"] == []

    raw = yaml.safe_load((vault_with_meta / "meta" / "relation-dictionary-user.yaml").read_text())
    entry = next(r for r in raw["relations"] if r["name"] == "assigned-to")
    assert entry["inverse_of"] == "relates-to"


def test_define_relation_inverse_of_unknown_gives_warning(vault_with_meta):
    """inverse_of naming a relation that doesn't exist yet produces a warning, not an error."""
    import api
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
        inverse_of="has-assignee",
    )
    assert result["defined"] is True
    assert any("has-assignee" in w for w in result["warnings"])


def test_define_relation_registry_reloads(vault_with_meta):
    import api
    from relation_registry import get_relation_registry
    api.define_relation(name="assigned-to", description="Assigned to entity.")
    reg = get_relation_registry(vault_with_meta)
    assert reg.is_valid("assigned-to")
    assert not reg.is_canonical("assigned-to")


def test_define_relation_second_entry_appends(vault_with_meta):
    import api
    api.define_relation(name="assigned-to", description="Assigned to entity.")
    api.define_relation(name="reviewed-by", description="Reviewed by entity.")

    raw = yaml.safe_load((vault_with_meta / "meta" / "relation-dictionary-user.yaml").read_text())
    names = [r["name"] for r in raw["relations"]]
    assert "assigned-to" in names
    assert "reviewed-by" in names


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

def test_define_relation_canonical_collision(vault_with_meta):
    import api
    result = api.define_relation(name="belongs-to", description="Collision.")
    assert result["defined"] is False
    assert any("belongs-to" in e for e in result["errors"])


def test_define_relation_empty_name(vault_with_meta):
    import api
    result = api.define_relation(name="", description="No name.")
    assert result["defined"] is False
    assert result["errors"]


def test_define_relation_asymmetric_inverse_warning(vault_with_meta):
    """inverse_of pointing to a canonical relation whose own inverse_of differs."""
    import api
    # "depends-on" has inverse_of="enables", not "assigned-to"
    result = api.define_relation(
        name="assigned-to",
        description="Assigned to entity.",
        inverse_of="depends-on",
    )
    assert result["defined"] is True
    assert any("asymmetric" in w for w in result["warnings"])


def test_define_relation_no_file_raises(tmp_path):
    import os, api
    vault = tmp_path / "vault"
    vault.mkdir()
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    try:
        with pytest.raises(FileNotFoundError):
            api.define_relation(name="assigned-to", description="No file.")
    finally:
        del os.environ["LOCI_VAULT_ROOT"]
        reset_relation_registry()

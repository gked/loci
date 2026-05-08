"""
tests/test_define_type.py
Tests for api.define_type — validate + write to ontology-user.yaml.
"""

import os
import shutil
import yaml
import pytest
from pathlib import Path

from type_registry import reset_registry, REFERENCES_DIR
from relation_registry import reset_relation_registry


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
    shutil.copy(REFERENCES_DIR / "ontology.yaml", meta / "ontology.yaml")
    shutil.copy(REFERENCES_DIR / "ontology-user.yaml", meta / "ontology-user.yaml")
    import os
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    yield vault
    del os.environ["LOCI_VAULT_ROOT"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_define_type_minimal(vault_with_meta):
    import api
    result = api.define_type(
        name="recipe",
        extends="procedure",
        description="A cooking procedure with ingredients.",
    )
    assert result == {"defined": True, "name": "recipe", "extends": "procedure"}

    raw = yaml.safe_load((vault_with_meta / "meta" / "ontology-user.yaml").read_text())
    assert any(t["name"] == "recipe" for t in raw["types"])


def test_define_type_with_fields(vault_with_meta):
    import api
    result = api.define_type(
        name="recipe",
        extends="procedure",
        description="A cooking procedure.",
        fields=[
            {"name": "cuisine", "type": "string"},
            {"name": "servings", "type": "string"},
        ],
    )
    assert result["defined"] is True

    raw = yaml.safe_load((vault_with_meta / "meta" / "ontology-user.yaml").read_text())
    entry = next(t for t in raw["types"] if t["name"] == "recipe")
    optional_names = [f["name"] for f in entry["fields"]["optional"]]
    assert "cuisine" in optional_names
    assert "servings" in optional_names


def test_define_type_with_enum_field(vault_with_meta):
    import api
    result = api.define_type(
        name="recipe",
        extends="procedure",
        description="A cooking procedure.",
        fields=[{"name": "difficulty", "type": "enum", "values": ["easy", "medium", "hard"]}],
    )
    assert result["defined"] is True

    raw = yaml.safe_load((vault_with_meta / "meta" / "ontology-user.yaml").read_text())
    entry = next(t for t in raw["types"] if t["name"] == "recipe")
    field = entry["fields"]["optional"][0]
    assert field["name"] == "difficulty"
    assert field["values"] == ["easy", "medium", "hard"]


def test_define_type_registry_reloads(vault_with_meta):
    import api
    from type_registry import get_registry
    api.define_type(name="recipe", extends="procedure", description="A cooking procedure.")
    reg = get_registry(vault_with_meta)
    assert "recipe" in reg.type_names()


def test_define_type_second_entry_appends(vault_with_meta):
    import api
    api.define_type(name="recipe", extends="procedure", description="A cooking procedure.")
    api.define_type(name="lab-note", extends="document", description="A research lab note.")

    raw = yaml.safe_load((vault_with_meta / "meta" / "ontology-user.yaml").read_text())
    names = [t["name"] for t in raw["types"]]
    assert "recipe" in names
    assert "lab-note" in names


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

def test_define_type_canonical_collision(vault_with_meta):
    import api
    result = api.define_type(name="task", extends="procedure", description="Collision.")
    assert result["defined"] is False
    assert any("task" in e for e in result["errors"])


def test_define_type_invalid_extends(vault_with_meta):
    import api
    result = api.define_type(name="my-type", extends="nonexistent", description="Bad parent.")
    assert result["defined"] is False
    assert any("nonexistent" in e for e in result["errors"])


def test_define_type_null_extends(vault_with_meta):
    import api
    result = api.define_type(name="my-type", extends=None, description="No parent.")
    assert result["defined"] is False
    assert result["errors"]


def test_define_type_inherited_field_redefinition(vault_with_meta):
    import api
    # "steps" is a required field on "procedure"
    result = api.define_type(
        name="recipe",
        extends="procedure",
        description="A cooking procedure.",
        fields=[{"name": "steps", "type": "array"}],
    )
    assert result["defined"] is False
    assert any("steps" in e for e in result["errors"])


def test_define_type_empty_name(vault_with_meta):
    import api
    result = api.define_type(name="", extends="procedure", description="No name.")
    assert result["defined"] is False
    assert result["errors"]


def test_define_type_invalid_name_format(vault_with_meta):
    import api
    result = api.define_type(name="My Type!", extends="procedure", description="Bad name.")
    assert result["defined"] is False
    assert any("valid type name" in e for e in result["errors"])


def test_define_type_invalid_field_type(vault_with_meta):
    import api
    result = api.define_type(
        name="recipe",
        extends="procedure",
        description="A cooking procedure.",
        fields=[{"name": "difficulty", "type": "badtype"}],
    )
    assert result["defined"] is False
    assert any("badtype" in e for e in result["errors"])


def test_define_type_no_file_raises(tmp_path):
    import api
    vault = tmp_path / "vault"
    vault.mkdir()
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    try:
        with pytest.raises(FileNotFoundError):
            api.define_type(name="recipe", extends="procedure", description="A cooking procedure.")
    finally:
        del os.environ["LOCI_VAULT_ROOT"]
        reset_registry()

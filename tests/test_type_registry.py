"""
tests/test_type_registry.py
Tests for tools/type_registry.py: TypeRegistry loading, user type validation,
inheritance, and the module-level singleton.
"""

import pytest
import yaml
from pathlib import Path

from type_registry import TypeRegistry, get_registry, reset_registry, REFERENCES_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ontology(path: Path, types: list[dict], base_fields: dict = None) -> None:
    content = {}
    if base_fields:
        content["base_fields"] = base_fields
    content["types"] = types
    path.write_text(yaml.dump(content), encoding="utf-8")


def _canonical_ontology() -> Path:
    return REFERENCES_DIR / "ontology.yaml"


# ---------------------------------------------------------------------------
# Loading canonical ontology
# ---------------------------------------------------------------------------

def test_loads_canonical_types():
    registry = TypeRegistry.load(_canonical_ontology())
    names = registry.type_names()
    for expected in ["document", "article", "task", "project", "entity",
                     "procedure", "topic", "bookmark", "conversation", "event"]:
        assert expected in names


def test_canonical_types_have_no_extends():
    registry = TypeRegistry.load(_canonical_ontology())
    for name in registry.type_names():
        td = registry.get(name)
        assert td.extends is None
        assert registry.is_canonical(name)


def test_task_has_status_required():
    registry = TypeRegistry.load(_canonical_ontology())
    task = registry.get("task")
    assert "status" in task.required_names()


def test_task_status_enum_includes_duplicate():
    registry = TypeRegistry.load(_canonical_ontology())
    task = registry.get("task")
    enums = task.enum_constraints()
    assert "duplicate" in enums["status"]


def test_entity_subtype_enum():
    registry = TypeRegistry.load(_canonical_ontology())
    entity = registry.get("entity")
    enums = entity.enum_constraints()
    assert enums["subtype"] == {"person", "organization", "place"}


def test_unknown_type_returns_none():
    registry = TypeRegistry.load(_canonical_ontology())
    assert registry.get("recipe") is None


# ---------------------------------------------------------------------------
# Loading user ontology — valid cases
# ---------------------------------------------------------------------------

def test_user_type_extends_canonical(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "recipe",
        "extends": "procedure",
        "description": "A cooking recipe.",
        "fields": {
            "optional": [{"name": "servings", "type": "string"}]
        }
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "recipe" in registry.type_names()
    assert not registry.is_canonical("recipe")


def test_user_type_inherits_parent_fields(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "recipe",
        "extends": "procedure",
        "description": "A cooking recipe.",
        "fields": {
            "optional": [{"name": "servings", "type": "string"}]
        }
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    recipe = registry.get("recipe")
    # Inherits 'steps' required from procedure
    assert "steps" in recipe.required_names()
    # Has its own optional field too
    optional_names = {f.name for f in recipe.optional_fields}
    assert "servings" in optional_names


def test_user_type_no_warnings_when_valid(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "recipe",
        "extends": "procedure",
        "description": "A cooking recipe.",
        "fields": {"optional": []}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert registry.warnings == []


# ---------------------------------------------------------------------------
# Loading user ontology — invalid cases (skipped with warnings)
# ---------------------------------------------------------------------------

def test_user_type_null_extends_skipped(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "newtype",
        "extends": None,
        "description": "A root type.",
        "fields": {"optional": []}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "newtype" not in registry.type_names()
    assert any("extends" in w for w in registry.warnings)


def test_user_type_unknown_parent_skipped(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "mytype",
        "extends": "nonexistent",
        "description": "Bad parent.",
        "fields": {"optional": []}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "mytype" not in registry.type_names()
    assert any("nonexistent" in w for w in registry.warnings)


def test_user_type_name_collision_skipped(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "task",
        "extends": "procedure",
        "description": "Collides with canonical.",
        "fields": {"optional": []}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    # task should still be the canonical one
    assert registry.is_canonical("task")
    assert any("collides" in w for w in registry.warnings)


def test_user_type_redefines_inherited_field_skipped(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "recipe",
        "extends": "procedure",
        "description": "Tries to redefine steps.",
        "fields": {
            "optional": [{"name": "steps", "type": "string"}]  # 'steps' is inherited
        }
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "recipe" not in registry.type_names()
    assert any("steps" in w for w in registry.warnings)


def test_user_extending_user_type_skipped(tmp_path):
    """Multi-level inheritance is blocked because user types aren't in canonical."""
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [
        {
            "name": "recipe",
            "extends": "procedure",
            "description": "Level 1.",
            "fields": {"optional": []}
        },
        {
            "name": "fancy-recipe",
            "extends": "recipe",   # recipe is user-defined, not canonical
            "description": "Level 2.",
            "fields": {"optional": []}
        }
    ])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "recipe" in registry.type_names()
    assert "fancy-recipe" not in registry.type_names()
    assert any("fancy-recipe" in w for w in registry.warnings)


def test_missing_user_file_is_safe():
    registry = TypeRegistry.load(_canonical_ontology(), Path("/nonexistent/ontology-user.yaml"))
    # Should load canonical only, no crash
    assert "task" in registry.type_names()
    assert registry.warnings == []


# ---------------------------------------------------------------------------
# validate_user_type
# ---------------------------------------------------------------------------

def test_validate_valid_type():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("recipe", "procedure", [
        {"name": "servings", "type": "string"}
    ])
    assert result["valid"] is True
    assert result["errors"] == []
    # resolved_fields includes inherited 'steps'
    required_names = [f["name"] for f in result["resolved_fields"]["required"]]
    assert "steps" in required_names


def test_validate_null_extends():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("mytype", "")
    assert result["valid"] is False
    assert any("extends" in e for e in result["errors"])


def test_validate_unknown_parent():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("mytype", "nonexistent")
    assert result["valid"] is False
    assert any("nonexistent" in e for e in result["errors"])


def test_validate_name_collision():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("task", "procedure")
    assert result["valid"] is False
    assert any("collides" in e for e in result["errors"])


def test_validate_redefines_inherited_field():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("recipe", "procedure", [
        {"name": "steps", "type": "string"}
    ])
    assert result["valid"] is False
    assert any("steps" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def test_get_registry_returns_registry():
    reset_registry()
    registry = get_registry()
    assert "task" in registry.type_names()


def test_get_registry_cached():
    reset_registry()
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_reset_registry_forces_reload():
    reset_registry()
    r1 = get_registry()
    reset_registry()
    r2 = get_registry()
    assert r1 is not r2

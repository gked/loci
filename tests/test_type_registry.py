"""
tests/test_type_registry.py
Tests for tools/type_registry.py: TypeRegistry loading, user type validation,
inheritance, and the module-level singleton.
"""

import pytest
import yaml
from pathlib import Path

from loci.tools.type_registry import TypeRegistry, get_registry, reset_registry, REFERENCES_DIR


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
                     "procedure", "topic", "bookmark", "conversation", "event", "log"]:
        assert expected in names


# The canonical types that specialise a root rather than being one.
CANONICAL_EXTENSIONS = {"skill": "procedure"}


def test_canonical_types_are_roots_or_known_extensions():
    registry = TypeRegistry.load(_canonical_ontology())
    for name in registry.type_names():
        td = registry.get(name)
        assert td.extends == CANONICAL_EXTENSIONS.get(name)
        assert registry.is_canonical(name)
    assert registry.warnings == []


def test_skill_is_canonical_and_extends_procedure():
    registry = TypeRegistry.load(_canonical_ontology())
    skill = registry.get("skill")
    assert skill.extends == "procedure"
    assert registry.is_canonical("skill")


def test_skill_inherits_procedure_fields():
    registry = TypeRegistry.load(_canonical_ontology())
    skill = registry.get("skill")
    procedure = registry.get("procedure")
    assert "steps" in skill.required_names()
    assert {f.name for f in procedure.optional_fields} <= {f.name for f in skill.optional_fields}
    assert {"triggers", "bundled_resources", "skill_version"} <= {f.name for f in skill.optional_fields}


def test_procedure_does_not_gain_skill_fields():
    registry = TypeRegistry.load(_canonical_ontology())
    names = {f.name for f in registry.get("procedure").optional_fields}
    assert "triggers" not in names


def test_canonical_extension_of_unknown_parent_skipped(tmp_path):
    canonical = tmp_path / "ontology.yaml"
    _write_ontology(canonical, [
        {"name": "orphan", "extends": "missing", "description": "No parent."},
    ])
    registry = TypeRegistry.load(canonical)
    assert "orphan" not in registry.type_names()
    assert any("orphan" in w for w in registry.warnings)


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


def test_log_has_subject_uid_required():
    registry = TypeRegistry.load(_canonical_ontology())
    log = registry.get("log")
    assert "subject_uid" in log.required_names()


def test_log_has_log_status_required():
    registry = TypeRegistry.load(_canonical_ontology())
    log = registry.get("log")
    assert "log_status" in log.required_names()


def test_log_status_enum():
    registry = TypeRegistry.load(_canonical_ontology())
    log = registry.get("log")
    enums = log.enum_constraints()
    assert enums["log_status"] == {"in-progress", "finished", "abandoned"}


def test_reading_log_returns_none():
    registry = TypeRegistry.load(_canonical_ontology())
    assert registry.get("reading-log") is None


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


def test_user_extending_canonical_extension_skipped(tmp_path):
    """`skill` is canonical but not a root; a user type may not nest beneath it."""
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "claude-skill",
        "extends": "skill",
        "description": "Level 2.",
        "fields": {"optional": []}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert "claude-skill" not in registry.type_names()
    assert any("claude-skill" in w for w in registry.warnings)


def test_user_type_named_skill_skipped_with_collision_warning(tmp_path):
    """A vault that still carries its own `skill` type gets a warning, not a crash."""
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{
        "name": "skill",
        "extends": "procedure",
        "description": "Old user copy.",
        "fields": {"optional": [{"name": "triggers", "type": "array"}]}
    }])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert registry.is_canonical("skill")
    assert any("skill" in w and "collides" in w for w in registry.warnings)


def test_validate_user_type_rejects_extending_skill():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("claude-skill", "skill")
    assert result["valid"] is False
    assert any("canonical root" in e for e in result["errors"])


def test_validate_user_type_rejects_name_skill():
    registry = TypeRegistry.load(_canonical_ontology())
    result = registry.validate_user_type("skill", "procedure")
    assert result["valid"] is False
    assert any("collides" in e for e in result["errors"])


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


# ---------------------------------------------------------------------------
# Subtype-specific fields
# ---------------------------------------------------------------------------

def test_asset_book_subtype_fields_loaded():
    registry = TypeRegistry.load(_canonical_ontology())
    asset = registry.get("asset")
    assert "book" in asset.subtype_fields


def test_asset_book_genre_enum_available():
    registry = TypeRegistry.load(_canonical_ontology())
    asset = registry.get("asset")
    enums = asset.enum_constraints(subtype="book")
    assert "genre" in enums
    assert "technology-computing" in enums["genre"]
    assert "fiction-literature" in enums["genre"]


def test_asset_genre_not_in_base_enum_constraints():
    """genre is subtype-specific — should not appear without subtype arg."""
    registry = TypeRegistry.load(_canonical_ontology())
    asset = registry.get("asset")
    enums = asset.enum_constraints()
    assert "genre" not in enums


def test_asset_non_book_subtype_has_no_genre():
    registry = TypeRegistry.load(_canonical_ontology())
    asset = registry.get("asset")
    enums = asset.enum_constraints(subtype="video")
    assert "genre" not in enums


def test_subtype_fields_parsed_from_yaml(tmp_path):
    onto = tmp_path / "ontology.yaml"
    _write_ontology(onto, [{
        "name": "asset",
        "extends": None,
        "description": "Test asset",
        "fields": {
            "required": [{"name": "subtype", "type": "enum", "values": ["book", "video"]}],
            "optional": [],
        },
        "subtypes": [
            {
                "name": "book",
                "fields": {
                    "optional": [{"name": "genre", "type": "enum", "values": ["fiction", "non-fiction"]}]
                }
            }
        ]
    }])
    registry = TypeRegistry.load(onto)
    asset = registry.get("asset")
    assert "book" in asset.subtype_fields
    enums = asset.enum_constraints(subtype="book")
    assert enums["genre"] == {"fiction", "non-fiction"}


# ---------------------------------------------------------------------------
# base_fields and is_canonical
# ---------------------------------------------------------------------------

def test_base_fields_come_from_the_ontology_file():
    registry = TypeRegistry.load(_canonical_ontology())
    declared = yaml.safe_load(_canonical_ontology().read_text(encoding="utf-8"))["base_fields"]
    assert registry.base_required == declared["required"]
    assert registry.base_optional == declared["optional"]
    assert "uid" in registry.base_required


def test_base_fields_follow_the_file_not_a_hardcoded_list(tmp_path):
    path = tmp_path / "ontology.yaml"
    _write_ontology(path, [{"name": "note", "extends": None, "description": "n"}],
                    base_fields={"required": ["uid", "colour"], "optional": []})
    assert TypeRegistry.load(path).base_required == ["uid", "colour"]


def test_a_vault_copy_without_base_fields_falls_back_to_the_packaged_list(tmp_path):
    path = tmp_path / "ontology.yaml"
    _write_ontology(path, [{"name": "note", "extends": None, "description": "n"}])
    registry = TypeRegistry.load(path)
    assert "uid" in registry.base_required
    assert registry.base_required == TypeRegistry.load(_canonical_ontology()).base_required


def test_is_canonical_means_defined_in_the_canonical_file(tmp_path):
    user_file = tmp_path / "ontology-user.yaml"
    _write_ontology(user_file, [{"name": "recipe", "extends": "procedure", "description": "r"}])
    registry = TypeRegistry.load(_canonical_ontology(), user_file)
    assert registry.is_canonical("procedure")
    assert not registry.is_canonical("recipe")
    assert not registry.is_canonical("no-such-type")

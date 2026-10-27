"""
tests/test_define_relation.py
Tests for api.define_relation — validate + write to relation-dictionary-user.yaml.
"""

import os
import shutil
import yaml
import pytest
from pathlib import Path

from loci.tools.type_registry import reset_registry
from loci.tools.relation_registry import reset_relation_registry, REFERENCES_DIR


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
    from loci import api
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
    from loci import api
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
    """inverse_of pointing to a user relation that has no inverse — no warning."""
    from loci import api
    user_path = vault_with_meta / "meta" / "relation-dictionary-user.yaml"
    api._append_yaml_entry(user_path, "relations", {"name": "has-assignee", "description": "Has."})
    reset_relation_registry()
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
        inverse_of="has-assignee",
    )
    assert result["defined"] is True
    assert result["warnings"] == []

    raw = yaml.safe_load(user_path.read_text())
    entry = next(r for r in raw["relations"] if r["name"] == "assigned-to")
    assert entry["inverse_of"] == "has-assignee"


def test_define_relation_inverse_of_symmetric_relation_gives_warning(vault_with_meta):
    """A symmetric relation is its own inverse, so it cannot name a new relation back."""
    from loci import api
    result = api.define_relation(
        name="assigned-to", description="Assigned.", inverse_of="relates-to"
    )
    assert result["defined"] is True
    assert any("symmetric" in w for w in result["warnings"])


def test_define_relation_inverse_of_unknown_gives_warning(vault_with_meta):
    """inverse_of naming a relation that doesn't exist yet produces a warning, not an error."""
    from loci import api
    result = api.define_relation(
        name="assigned-to",
        description="This task is assigned to the linked entity.",
        inverse_of="has-assignee",
    )
    assert result["defined"] is True
    assert any("has-assignee" in w for w in result["warnings"])


def test_define_relation_registry_reloads(vault_with_meta):
    from loci import api
    from loci.tools.relation_registry import get_relation_registry
    api.define_relation(name="assigned-to", description="Assigned to entity.")
    reg = get_relation_registry(vault_with_meta)
    assert reg.is_valid("assigned-to")
    assert not reg.is_canonical("assigned-to")


def test_define_relation_second_entry_appends(vault_with_meta):
    from loci import api
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
    from loci import api
    result = api.define_relation(name="belongs-to", description="Collision.")
    assert result["defined"] is False
    assert any("belongs-to" in e for e in result["errors"])


def test_define_relation_empty_name(vault_with_meta):
    from loci import api
    result = api.define_relation(name="", description="No name.")
    assert result["defined"] is False
    assert result["errors"]


def test_define_relation_asymmetric_inverse_warning(vault_with_meta):
    """inverse_of pointing to a canonical relation whose own inverse_of differs."""
    from loci import api
    # "depends-on" has inverse_of="enables", not "assigned-to"
    result = api.define_relation(
        name="assigned-to",
        description="Assigned to entity.",
        inverse_of="depends-on",
    )
    assert result["defined"] is True
    assert any("asymmetric" in w for w in result["warnings"])


def test_define_relation_no_file_raises(tmp_path):
    from loci import api
    vault = tmp_path / "vault"
    vault.mkdir()
    os.environ["LOCI_VAULT_ROOT"] = str(vault)
    try:
        with pytest.raises(FileNotFoundError):
            api.define_relation(name="assigned-to", description="No file.")
    finally:
        del os.environ["LOCI_VAULT_ROOT"]
        reset_relation_registry()


# ---------------------------------------------------------------------------
# symmetric and back-reference
# ---------------------------------------------------------------------------

def _user_relations(vault):
    raw = yaml.safe_load((vault / "meta" / "relation-dictionary-user.yaml").read_text())
    return {r["name"]: r for r in raw["relations"]}


def test_define_relation_symmetric_is_written(vault_with_meta):
    from loci import api
    result = api.define_relation(
        name="collaborates-with", description="Works with the linked entity.", symmetric=True
    )
    assert result["defined"] is True
    assert _user_relations(vault_with_meta)["collaborates-with"]["symmetric"] is True


def test_define_relation_symmetric_with_inverse_of_is_refused(vault_with_meta):
    from loci import api
    result = api.define_relation(
        name="collaborates-with", description="Works with.", inverse_of="depends-on", symmetric=True
    )
    assert result["defined"] is False
    assert any("symmetric" in e for e in result["errors"])
    assert _user_relations(vault_with_meta) == {}


def test_define_relation_names_itself_on_a_user_inverse(vault_with_meta):
    """Defining B with inverse_of=A writes inverse_of=B onto A when A has no inverse."""
    from loci import api
    user_path = vault_with_meta / "meta" / "relation-dictionary-user.yaml"
    api._append_yaml_entry(user_path, "relations", {"name": "assigned-to", "description": "Assigned."})
    reset_relation_registry()

    result = api.define_relation(
        name="has-assignee", description="Has the linked assignee.", inverse_of="assigned-to"
    )
    assert result["defined"] is True
    rels = _user_relations(vault_with_meta)
    assert rels["assigned-to"]["inverse_of"] == "has-assignee"
    assert rels["has-assignee"]["inverse_of"] == "assigned-to"

    from loci.tools.relation_registry import get_relation_registry
    assert get_relation_registry(vault_with_meta).inverse_problems() == []


def test_define_relation_leaves_a_canonical_inverse_alone(vault_with_meta):
    from loci import api
    canonical = (vault_with_meta / "meta" / "relation-dictionary.yaml").read_text()
    api.define_relation(name="needs", description="Needs.", inverse_of="depends-on")
    assert (vault_with_meta / "meta" / "relation-dictionary.yaml").read_text() == canonical
    assert "inverse_of" not in _user_relations(vault_with_meta).get("depends-on", {})

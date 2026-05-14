"""
tests/test_scheme_registry.py
Tests for tools/scheme_registry.py: SchemeRegistry class and singleton.
"""

import pytest
import yaml
from pathlib import Path

from scheme_registry import (
    SchemeRegistry,
    SchemeDef,
    get_scheme_registry,
    reset_scheme_registry,
    REFERENCES_DIR,
)


@pytest.fixture(autouse=True)
def reset():
    reset_scheme_registry()
    yield
    reset_scheme_registry()


@pytest.fixture(scope="module")
def canonical_registry():
    return SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml")


# ---------------------------------------------------------------------------
# Loading canonical schemes
# ---------------------------------------------------------------------------

def test_loads_canonical_schemes(canonical_registry):
    names = canonical_registry.scheme_names()
    assert "local" in names
    assert "google-drive" in names
    assert "url" in names
    assert "s3" in names
    assert len(names) == 10  # all 10 canonical schemes


def test_local_scheme_def(canonical_registry):
    sd = canonical_registry.get("local")
    assert sd is not None
    assert sd.name == "local"
    assert "path" in sd.required_fields
    assert "resolve" in sd.capabilities
    assert "enumerate" in sd.capabilities


def test_url_scheme_no_enumerate(canonical_registry):
    sd = canonical_registry.get("url")
    assert "url" in sd.required_fields
    assert "resolve" in sd.capabilities
    assert "enumerate" not in sd.capabilities


def test_s3_optional_fields(canonical_registry):
    sd = canonical_registry.get("s3")
    assert "bucket" in sd.required_fields
    assert "key" in sd.required_fields
    assert "region" in sd.optional_fields


def test_ssh_remote_multi_required(canonical_registry):
    sd = canonical_registry.get("ssh-remote")
    assert "host" in sd.required_fields
    assert "path" in sd.required_fields
    assert "user" in sd.optional_fields
    assert "port" in sd.optional_fields


def test_is_valid_known_scheme(canonical_registry):
    assert canonical_registry.is_valid("local") is True
    assert canonical_registry.is_valid("google-drive") is True


def test_is_valid_unknown_scheme(canonical_registry):
    assert canonical_registry.is_valid("ftp") is False
    assert canonical_registry.is_valid("") is False


def test_get_unknown_scheme_returns_none(canonical_registry):
    assert canonical_registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# User scheme loading
# ---------------------------------------------------------------------------

def test_user_scheme_additive(tmp_path):
    user_yaml = tmp_path / "scheme-dictionary-user.yaml"
    user_yaml.write_text(
        "schemes:\n  - name: my-store\n    description: Custom store\n"
        "    required_fields: [bucket]\n    capabilities: [resolve]\n",
        encoding="utf-8",
    )
    reg = SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml", user_yaml)
    assert reg.is_valid("local")      # canonical still present
    assert reg.is_valid("my-store")   # user scheme added
    sd = reg.get("my-store")
    assert "bucket" in sd.required_fields
    assert "resolve" in sd.capabilities


def test_user_scheme_collision_skipped(tmp_path):
    user_yaml = tmp_path / "scheme-dictionary-user.yaml"
    user_yaml.write_text(
        "schemes:\n  - name: local\n    description: Overriding local\n"
        "    required_fields: [path]\n    capabilities: [resolve]\n",
        encoding="utf-8",
    )
    reg = SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml", user_yaml)
    assert len(reg.warnings) == 1
    assert "collides" in reg.warnings[0]
    # Canonical definition must be preserved
    assert "enumerate" in reg.get("local").capabilities


def test_user_scheme_missing_name_skipped(tmp_path):
    user_yaml = tmp_path / "scheme-dictionary-user.yaml"
    user_yaml.write_text(
        "schemes:\n  - description: No name\n    required_fields: [x]\n    capabilities: [resolve]\n",
        encoding="utf-8",
    )
    reg = SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml", user_yaml)
    assert any("missing 'name'" in w for w in reg.warnings)


def test_empty_user_file_ok(tmp_path):
    user_yaml = tmp_path / "scheme-dictionary-user.yaml"
    user_yaml.write_text("schemes: []\n", encoding="utf-8")
    reg = SchemeRegistry.load(REFERENCES_DIR / "scheme-dictionary.yaml", user_yaml)
    assert reg.warnings == []
    assert reg.is_valid("local")


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------

def test_get_scheme_registry_returns_same_instance():
    r1 = get_scheme_registry()
    r2 = get_scheme_registry()
    assert r1 is r2


def test_reset_forces_reload():
    r1 = get_scheme_registry()
    reset_scheme_registry()
    r2 = get_scheme_registry()
    assert r1 is not r2


def test_fallback_to_references_when_no_vault_meta(tmp_path):
    vault_no_meta = tmp_path / "vault"
    vault_no_meta.mkdir()
    reg = get_scheme_registry(vault_no_meta)
    assert reg.is_valid("local")   # loaded from REFERENCES_DIR fallback

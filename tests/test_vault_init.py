"""
tests/test_vault_init.py
Tests for tools/vault_init.py: load_config, create_vault_structure,
reseed_meta, and check_meta_version.
"""

import os
import yaml
import pytest
from pathlib import Path

import vault_init
from vault_init import (
    load_config,
    create_vault_structure,
    reseed_meta,
    check_meta_version,
    META_VERSION,
    META_FILES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_loci_vault_root_env(monkeypatch):
    """Ensure LOCI_VAULT_ROOT is unset for tests that check config file fallback."""
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)


@pytest.fixture
def fake_config_path(tmp_path, monkeypatch):
    """Point vault_init.CONFIG_PATH at a temp file."""
    config_file = tmp_path / "config.yml"
    monkeypatch.setattr(vault_init, "CONFIG_PATH", config_file)
    return config_file


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

def test_load_config_env_var_takes_precedence(monkeypatch, fake_config_path):
    fake_config_path.write_text("vault_root: /from-file\n", encoding="utf-8")
    monkeypatch.setenv("LOCI_VAULT_ROOT", "/from-env")
    result = load_config()
    assert result == {"vault_root": "/from-env"}


def test_load_config_reads_config_file(fake_config_path):
    fake_config_path.write_text("vault_root: /my/vault\nmeta_version: 2\n", encoding="utf-8")
    result = load_config()
    assert result["vault_root"] == "/my/vault"
    assert result["meta_version"] == 2


def test_load_config_returns_none_when_nothing_configured(fake_config_path):
    # fake_config_path exists as a fixture object but we never write to it
    assert not fake_config_path.exists()
    result = load_config()
    assert result is None


# ---------------------------------------------------------------------------
# create_vault_structure
# ---------------------------------------------------------------------------

def test_create_vault_structure_creates_meta_folder(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    assert (vault_root / "meta").is_dir()


def test_create_vault_structure_creates_asset_dirs(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    loci_root = tmp_path
    assert (loci_root / "assets").is_dir()
    assert (loci_root / "asset-registry" / ".pending").is_dir()


def test_create_vault_structure_seeds_meta_files(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    for fname in META_FILES:
        p = vault_root / "meta" / fname
        assert p.exists(), f"Missing seeded meta file: {fname}"
        assert p.stat().st_size > 0


def test_create_vault_structure_does_not_overwrite_existing_meta(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    # Overwrite one meta file with custom content
    custom = vault_root / "meta" / "tag-dictionary.md"
    custom.write_text("# my custom tags\n", encoding="utf-8")
    # Call again — should not overwrite
    create_vault_structure(vault_root)
    assert custom.read_text(encoding="utf-8") == "# my custom tags\n"


def test_create_vault_structure_idempotent(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    create_vault_structure(vault_root)  # should not raise
    assert (vault_root / "meta").is_dir()


# ---------------------------------------------------------------------------
# reseed_meta
# ---------------------------------------------------------------------------

def test_reseed_meta_overwrites_existing(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    tag_dict = vault_root / "meta" / "tag-dictionary.md"
    tag_dict.write_text("# custom content\n", encoding="utf-8")
    reseed_meta(vault_root)
    # Should now contain the reference content, not the custom content
    assert tag_dict.read_text(encoding="utf-8") != "# custom content\n"


def test_reseed_meta_restores_all_files(tmp_path):
    vault_root = tmp_path / "vault"
    (vault_root / "meta").mkdir(parents=True)
    reseed_meta(vault_root)
    for fname in META_FILES:
        assert (vault_root / "meta" / fname).exists()


# ---------------------------------------------------------------------------
# check_meta_version
# ---------------------------------------------------------------------------

def test_check_meta_version_skips_when_env_var_set(monkeypatch, fake_config_path):
    monkeypatch.setenv("LOCI_VAULT_ROOT", "/some/path")
    result = check_meta_version()
    assert result is None


def test_check_meta_version_skips_when_no_config_file(fake_config_path):
    assert not fake_config_path.exists()
    result = check_meta_version()
    assert result is None


def test_check_meta_version_no_op_when_current(tmp_path, fake_config_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION}),
        encoding="utf-8",
    )
    result = check_meta_version()
    assert result is None


def test_check_meta_version_reseeds_when_outdated(tmp_path, fake_config_path, monkeypatch):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    # Mark a meta file as stale
    stale = vault_root / "meta" / "tag-dictionary.md"
    stale.write_text("# stale content\n", encoding="utf-8")

    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION - 1}),
        encoding="utf-8",
    )

    result = check_meta_version()
    assert result is not None
    assert "updated" in result.lower()
    # Config meta_version bumped
    updated_config = yaml.safe_load(fake_config_path.read_text(encoding="utf-8"))
    assert updated_config["meta_version"] == META_VERSION
    # Stale file reseeded
    assert stale.read_text(encoding="utf-8") != "# stale content\n"


def test_check_meta_version_reseeds_when_unversioned(tmp_path, fake_config_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    # Config with no meta_version key
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root)}),
        encoding="utf-8",
    )
    result = check_meta_version()
    assert result is not None
    assert "unversioned" in result


# ---------------------------------------------------------------------------
# setup_interactive
# ---------------------------------------------------------------------------

def test_setup_interactive_with_vault_and_remote(tmp_path, monkeypatch):
    from vault_init import setup_interactive
    vault_path = str(tmp_path / "vault")
    responses = iter([vault_path, "nextcloud", "loci-remote"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    config = setup_interactive()
    assert config["vault_root"] == vault_path
    assert config["sync_remote"] == "nextcloud"
    assert config["sync_remote_path"] == "loci-remote"
    assert config["meta_version"] == META_VERSION


def test_setup_interactive_with_defaults(tmp_path, monkeypatch):
    from vault_init import setup_interactive
    # Empty input → use defaults
    monkeypatch.setattr("builtins.input", lambda _: "")
    config = setup_interactive()
    assert "knowledge-vault" in config["vault_root"]
    assert config["sync_remote"] is None


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def test_init_existing_config_no_force(tmp_path, fake_config_path):
    from vault_init import init
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION}),
        encoding="utf-8",
    )
    result = init(force=False)
    assert result["vault_root"] == str(vault_root)
    assert (vault_root / "meta").is_dir()


def test_init_existing_config_force(tmp_path, fake_config_path):
    from vault_init import init
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    # Mark a meta file as stale
    stale = vault_root / "meta" / "tag-dictionary.md"
    stale.write_text("# stale\n", encoding="utf-8")
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION}),
        encoding="utf-8",
    )
    result = init(force=True)
    assert result["meta_version"] == META_VERSION
    assert stale.read_text(encoding="utf-8") != "# stale\n"


def test_init_no_config_creates_new(tmp_path, fake_config_path, monkeypatch):
    from vault_init import init
    vault_path = str(tmp_path / "new-vault")
    responses = iter([vault_path, "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    result = init()
    assert result["vault_root"] == vault_path
    assert fake_config_path.exists()
    assert Path(vault_path).is_dir()

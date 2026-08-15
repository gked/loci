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
    ensure_env_vault,
    read_vault_meta_version,
    write_vault_meta_version,
    META_VERSION,
    META_FILES,
    USER_META_FILES,
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
# ontology-guide.md — the user's guide travels with the vault
# ---------------------------------------------------------------------------

def test_ontology_guide_is_seeded_on_setup(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    guide = vault_root / "meta" / "ontology-guide.md"
    assert guide.exists(), "the user's ontology guide must be seeded into the vault"
    assert guide.read_text(encoding="utf-8").startswith("# The Ontology")


def test_ontology_guide_is_refreshed_on_version_bump(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    guide = vault_root / "meta" / "ontology-guide.md"
    guide.write_text("# stale guide\n", encoding="utf-8")
    reseed_meta(vault_root)
    assert guide.read_text(encoding="utf-8") != "# stale guide\n"


def test_ontology_guide_ships_under_server(tmp_path):
    # deploy/Dockerfile copies only server/ — a seed source outside it is missing
    # in the image, so seeding would fail for every Docker user.
    repo_root = Path(vault_init.__file__).parent.parent.parent
    src = vault_init.REFERENCES_DIR / "ontology-guide.md"
    assert src.exists()
    assert src.is_relative_to(repo_root / "server")


# ---------------------------------------------------------------------------
# ensure_env_vault — the LOCI_VAULT_ROOT (Docker) path
# ---------------------------------------------------------------------------

def test_ensure_env_vault_seeds_empty_vault(tmp_path):
    """A bare bind mount is what Docker gives us on first run."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    notice = ensure_env_vault(vault_root)

    assert notice is not None and "seeded" in notice
    for filename in META_FILES + USER_META_FILES:
        assert (vault_root / "meta" / filename).exists(), filename
    assert read_vault_meta_version(vault_root) == META_VERSION


def test_ensure_env_vault_does_not_seed_a_missing_vault_dir(tmp_path):
    """No directory means no mount: seeding it would write to the container's
    own layer and report success for files that vanish on the next run."""
    vault_root = tmp_path / "not-yet-there"

    notice = ensure_env_vault(vault_root)

    assert not vault_root.exists()
    assert notice is not None
    assert "not mounted" in notice or "does not exist" in notice


def test_ensure_env_vault_missing_dir_notice_names_the_path(tmp_path, capsys):
    vault_root = tmp_path / "not-yet-there"

    ensure_env_vault(vault_root)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(vault_root) in captured.err


def test_ensure_env_vault_does_not_create_siblings(tmp_path):
    """Siblings would land outside the bind mount and vanish on restart."""
    vault_root = tmp_path / "parent" / "vault"
    vault_root.mkdir(parents=True)

    ensure_env_vault(vault_root)

    assert not (vault_root.parent / "assets").exists()
    assert not (vault_root.parent / "asset-registry").exists()
    assert not (vault_root.parent / "loci-stage").exists()


def test_ensure_env_vault_no_op_when_current(tmp_path):
    """Scenario 2: vault already set up at the current version — leave it alone."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    ensure_env_vault(vault_root)  # seed it
    (vault_root / "meta" / "ontology.yaml").write_text("user edited\n")

    notice = ensure_env_vault(vault_root)

    assert notice is None
    assert (vault_root / "meta" / "ontology.yaml").read_text() == "user edited\n"


def test_ensure_env_vault_reseeds_when_outdated(tmp_path):
    """Scenario 3: existing vault, older meta — reseed canonical files only."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    ensure_env_vault(vault_root)
    write_vault_meta_version(vault_root, META_VERSION - 1)
    (vault_root / "meta" / "ontology.yaml").write_text("stale\n")
    (vault_root / "meta" / "ontology-user.yaml").write_text("mine\n")

    notice = ensure_env_vault(vault_root)

    assert notice is not None and "updated" in notice
    assert (vault_root / "meta" / "ontology.yaml").read_text() != "stale\n"
    # user-owned files survive the upgrade
    assert (vault_root / "meta" / "ontology-user.yaml").read_text() == "mine\n"
    assert read_vault_meta_version(vault_root) == META_VERSION


def test_ensure_env_vault_adopts_complete_unversioned_vault(tmp_path):
    """A wizard-made vault has a full meta/ but no marker — only this path
    writes one. Reseeding it would destroy the user's own dictionaries."""
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)  # the local setup flow, no marker written
    tags = vault_root / "meta" / "tag-dictionary.md"
    tags.write_text("# my curated tags\n", encoding="utf-8")

    notice = ensure_env_vault(vault_root)

    assert notice is None
    assert tags.read_text(encoding="utf-8") == "# my curated tags\n"
    assert read_vault_meta_version(vault_root) == META_VERSION


def test_ensure_env_vault_adoption_fills_missing_user_meta_files(tmp_path):
    """Adopting must still complete the vault, just never overwrite it."""
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    (vault_root / "meta" / "ontology-user.yaml").unlink()

    ensure_env_vault(vault_root)

    assert (vault_root / "meta" / "ontology-user.yaml").exists()


def test_ensure_env_vault_reseeds_when_unversioned_and_incomplete(tmp_path):
    """A partial meta/ is not evidence of a current vault — repair it."""
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    (vault_root / "meta" / "ontology.yaml").unlink()

    notice = ensure_env_vault(vault_root)

    assert notice is not None and "unversioned" in notice
    assert (vault_root / "meta" / "ontology.yaml").exists()
    assert read_vault_meta_version(vault_root) == META_VERSION


def test_ensure_env_vault_writes_nothing_to_stdout(tmp_path, capsys):
    """Under stdio transport stdout is the JSON-RPC channel — keep it clean."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    ensure_env_vault(vault_root)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "seeded" in captured.err


def test_describe_vault_location_plain_path_when_not_a_mount(tmp_path):
    """A normal directory is not a mount point, so report it as-is."""
    assert vault_init.describe_vault_location(tmp_path) == str(tmp_path)


def test_describe_vault_location_reports_host_path(tmp_path, monkeypatch):
    """In a container the mount point alone doesn't tell the user where to look."""
    monkeypatch.setattr(
        vault_init,
        "_host_path_for_mount",
        lambda _root: "/Users/someone/loci/vault",
    )
    result = vault_init.describe_vault_location(Path("/knowledge-vault"))
    assert "/Users/someone/loci/vault" in result
    assert "/knowledge-vault" in result


def test_host_path_for_mount_reads_bind_mount_source(tmp_path):
    """The real format, as produced by the container during verification."""
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "433 424 0:37 /Users/you/loci/vault /knowledge-vault "
        "rw,relatime - virtiofs mac rw\n"
    )
    result = vault_init._host_path_for_mount(Path("/knowledge-vault"), mountinfo)
    assert result == "/Users/you/loci/vault"


def test_host_path_for_mount_ignores_docker_named_volumes(tmp_path):
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "433 424 0:37 /var/lib/docker/volumes/loci/_data /vault rw - ext4 x rw\n"
    )
    assert vault_init._host_path_for_mount(Path("/vault"), mountinfo) is None


def test_host_path_for_mount_returns_none_when_unmounted(tmp_path):
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text("433 424 0:37 /elsewhere /other rw - ext4 x rw\n")
    assert vault_init._host_path_for_mount(Path("/vault"), mountinfo) is None


def test_host_path_for_mount_matches_mount_point_containing_a_space(tmp_path):
    """mountinfo octal-escapes whitespace; an unescaped compare never matches."""
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "433 424 0:37 /Users/me/My\\040Files/vault /knowledge\\040vault "
        "rw,relatime - virtiofs mac rw\n"
    )
    result = vault_init._host_path_for_mount(Path("/knowledge vault"), mountinfo)
    assert result == "/Users/me/My Files/vault"


def test_host_path_for_mount_leaves_literal_backslash_alone(tmp_path):
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text("433 424 0:37 /srv/a\\134b /vault rw - ext4 x rw\n")
    assert vault_init._host_path_for_mount(Path("/vault"), mountinfo) == "/srv/a\\b"


def test_host_path_for_mount_takes_the_last_matching_line(tmp_path):
    """A later entry for the same mount point overmounts the earlier one."""
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "433 424 0:37 /host/old /vault rw - ext4 x rw\n"
        "440 424 0:38 /host/new /vault rw - ext4 x rw\n"
    )
    assert vault_init._host_path_for_mount(Path("/vault"), mountinfo) == "/host/new"


def test_read_vault_meta_version_handles_corrupt_marker(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    ensure_env_vault(vault_root)
    (vault_root / "meta" / vault_init.VERSION_MARKER).write_text("not-a-number\n")

    assert read_vault_meta_version(vault_root) is None


# ---------------------------------------------------------------------------
# check_meta_version
# ---------------------------------------------------------------------------

def test_check_meta_version_seeds_env_vault(monkeypatch, fake_config_path, tmp_path):
    """Docker mounts an empty vault: startup must seed it rather than skip."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(vault_root))

    notice = check_meta_version()

    assert notice is not None and "seeded" in notice
    for filename in META_FILES + USER_META_FILES:
        assert (vault_root / "meta" / filename).exists(), filename
    assert read_vault_meta_version(vault_root) == META_VERSION


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


def test_check_meta_version_records_marker_in_vault_on_reseed(tmp_path, fake_config_path):
    """Config mode must leave the same marker the Docker path reads, or that
    path sees the vault as unversioned and reseeds over the user's files."""
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION - 1}),
        encoding="utf-8",
    )

    check_meta_version()

    assert read_vault_meta_version(vault_root) == META_VERSION


def test_check_meta_version_records_marker_when_already_current(tmp_path, fake_config_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION}),
        encoding="utf-8",
    )

    assert check_meta_version() is None
    assert read_vault_meta_version(vault_root) == META_VERSION


def test_check_meta_version_config_branch_writes_nothing_to_stdout(tmp_path, fake_config_path, capsys):
    """reseed_meta and save_config both print — and stdout is the JSON-RPC
    channel under stdio transport, in config mode just as much as in Docker."""
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    fake_config_path.write_text(
        yaml.dump({"vault_root": str(vault_root), "meta_version": META_VERSION - 1}),
        encoding="utf-8",
    )
    capsys.readouterr()  # discard create_vault_structure's own output

    assert check_meta_version() is not None
    assert capsys.readouterr().out == ""


def test_check_meta_version_ignores_config_without_vault_root(fake_config_path):
    fake_config_path.write_text(yaml.dump({"meta_version": 1}), encoding="utf-8")
    assert check_meta_version() is None


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
# field-dictionary schema assertions
# ---------------------------------------------------------------------------

def test_field_dictionary_task_status_includes_duplicate(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    field_dict = (vault_root / "meta" / "field-dictionary.md").read_text(encoding="utf-8")
    task_status_line = next(
        line for line in field_dict.splitlines()
        if "todo" in line and "done" in line
    )
    assert "duplicate" in task_status_line


# ---------------------------------------------------------------------------
# USER_META_FILES — seeded once, never reseeded
# ---------------------------------------------------------------------------

def test_user_meta_files_seeded_on_create(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    for fname in USER_META_FILES:
        p = vault_root / "meta" / fname
        assert p.exists(), f"User meta file not seeded: {fname}"
        assert p.stat().st_size > 0


def test_user_meta_files_not_overwritten_by_create(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    user_file = vault_root / "meta" / "ontology-user.yaml"
    user_file.write_text("# my custom types\ntypes: [{name: recipe}]\n", encoding="utf-8")
    create_vault_structure(vault_root)  # second call
    assert "recipe" in user_file.read_text(encoding="utf-8")


def test_user_meta_files_not_overwritten_by_reseed(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    user_file = vault_root / "meta" / "ontology-user.yaml"
    user_file.write_text("# my custom types\ntypes: [{name: recipe}]\n", encoding="utf-8")
    reseed_meta(vault_root)
    assert "recipe" in user_file.read_text(encoding="utf-8")


def test_reseed_meta_still_updates_canonical_files(tmp_path):
    vault_root = tmp_path / "vault"
    create_vault_structure(vault_root)
    canonical = vault_root / "meta" / "ontology.yaml"
    canonical.write_text("# stale ontology\n", encoding="utf-8")
    reseed_meta(vault_root)
    assert "# stale ontology" not in canonical.read_text(encoding="utf-8")


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

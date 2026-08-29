"""
tests/test_run_preflight.py
The preflight `make run` shells out to (scripts/run_preflight.py).

Its whole job is to agree with the servers about which directory is going to be
served. Every case here is one where a cheaper shell extraction disagreed: an
inline comment or a quote in a hand-edited config, a `~alice` path, or an
install that sets LOCI_VAULT_ROOT and never writes a config file at all —
load_config() short-circuits on the env var before it opens one.
"""
import getpass
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_preflight import (  # noqa: E402  (must follow sys.path insert)
    PreflightError,
    main,
    resolve_vault,
)


def _config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "config.yml"
    config.write_text(body, encoding="utf-8")
    return config


def test_an_inline_comment_is_not_part_of_the_path(tmp_path):
    """
    yaml.safe_load() drops it, so the server serves /vault. Taking the rest of
    the line instead rejected a config that works.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    config = _config(tmp_path, f"vault_root: {vault}  # the laptop's copy\n")

    assert resolve_vault(config) == vault


def test_trailing_whitespace_is_not_part_of_the_path(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    config = _config(tmp_path, f"vault_root: {vault}   \n")

    assert resolve_vault(config) == vault


def test_an_apostrophe_inside_the_path_survives(tmp_path):
    """Stripping every quote in the value turned Bob's Vault into Bobs Vault."""
    vault = tmp_path / "Bob's Vault"
    vault.mkdir()
    config = _config(tmp_path, f'vault_root: "{vault}"\n')

    assert resolve_vault(config) == vault


def test_a_named_tilde_is_expanded_like_expanduser(tmp_path):
    """
    Path.expanduser() resolves `~alice/vault` as well as `~/vault`, so a config
    carrying the named form has to resolve to the same directory here. Uses the
    user running the suite, the one name that is certain to be resolvable.
    """
    config = _config(tmp_path, f"vault_root: ~{getpass.getuser()}/knowledge\n")

    assert resolve_vault(config) == Path.home() / "knowledge"


def test_a_quoted_lone_tilde_is_the_home_directory(tmp_path):
    """
    Quoted, because an unquoted `~` is YAML's null: load_config() reads that as
    no vault_root at all, and so does this.
    """
    assert resolve_vault(_config(tmp_path, 'vault_root: "~"\n')) == Path.home()

    with pytest.raises(PreflightError, match="no vault_root"):
        resolve_vault(_config(tmp_path, "vault_root: ~\n"))


def test_the_env_vault_root_needs_no_config_file_at_all(tmp_path):
    """
    load_config() returns {"vault_root": ...} from the environment without
    opening the config, so requiring the file rejected an install that runs.
    """
    vault = tmp_path / "vault"
    vault.mkdir()

    assert resolve_vault(tmp_path / "nothing-here.yml", str(vault)) == vault


def test_the_env_vault_root_wins_over_a_configured_one(tmp_path):
    config = _config(tmp_path, f"vault_root: {tmp_path / 'configured'}\n")

    assert resolve_vault(config, str(tmp_path / "environment")) == tmp_path / "environment"


def test_a_missing_config_names_the_path_and_the_fix(tmp_path):
    with pytest.raises(PreflightError) as exc:
        resolve_vault(tmp_path / "config.yml")

    assert str(tmp_path / "config.yml") in str(exc.value)
    assert "setup.py" in str(exc.value)


def test_a_config_without_a_vault_root_is_reported(tmp_path):
    with pytest.raises(PreflightError, match="no vault_root"):
        resolve_vault(_config(tmp_path, "api_token: abc123\n"))


def test_a_config_that_is_not_a_mapping_is_reported(tmp_path):
    """An empty file parses to None; a stray list to a list. Neither has one."""
    with pytest.raises(PreflightError, match="no vault_root"):
        resolve_vault(_config(tmp_path, ""))


def test_unparseable_yaml_says_so_instead_of_traceback(tmp_path):
    with pytest.raises(PreflightError, match="not valid YAML"):
        resolve_vault(_config(tmp_path, "vault_root: [unclosed\n"))


def test_main_names_the_vault_it_will_serve(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    vault = tmp_path / "vault"
    vault.mkdir()
    config = _config(tmp_path, f"vault_root: {vault}\n")

    assert main([str(config)]) == 0
    assert f"serving {vault}" in capsys.readouterr().out


def test_main_reports_a_vault_root_that_is_not_on_disk(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    absent = tmp_path / "unmounted-drive" / "vault"
    config = _config(tmp_path, f"vault_root: {absent}\n")

    assert main([str(config)]) == 1
    err = capsys.readouterr().err
    assert str(absent) in err and "does not exist" in err

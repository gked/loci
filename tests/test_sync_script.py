"""
tests/test_sync_script.py
Config resolution in sync/sync.sh.

The script is a user-facing entrypoint that reads config.yml itself, so it has
to resolve the file the same way config_path() in vault_init.py does. When the
config moved to ~/.config/loci, a script still looking in the project root broke
for every existing user the moment the server migrated their file — with an
error that pointed nowhere near the cause.

Each case runs the real script against a copy in a temp checkout, with stubbed
`rclone` and `python3` on PATH, and reads the vault root back off the banner it
prints before syncing.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SYNC_SCRIPT = Path(__file__).parent.parent / "sync" / "sync.sh"


@pytest.fixture
def sync_env(tmp_path):
    """
    A temp checkout holding a copy of sync.sh, plus a stub bin/ on PATH.

    The script is copied rather than run in place so the project-root fallback
    case can write a config.yml next to it without touching the real checkout.
    """
    checkout = tmp_path / "checkout"
    (checkout / "sync").mkdir(parents=True)
    script = checkout / "sync" / "sync.sh"
    shutil.copy2(SYNC_SCRIPT, script)

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    # rclone must exist but must not run: the banner is printed before it.
    (stub_bin / "rclone").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    # The script parses YAML with python3; pin it to the interpreter running the
    # tests so it is guaranteed to have PyYAML.
    (stub_bin / "python3").write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8"
    )
    for stub in stub_bin.iterdir():
        stub.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": f"{stub_bin}:{os.environ['PATH']}",
        "HOME": str(home),
    }
    return script, env, home


def _write_config(path: Path, vault_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"vault_root": str(vault_root), "sync_remote": "gdrive"}),
        encoding="utf-8",
    )


def _run(script: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), "push"],
        env=env, capture_output=True, text=True, timeout=60,
    )


def test_reads_the_user_level_config(sync_env, tmp_path):
    """The location the server migrates to — the default for every install."""
    script, env, home = sync_env
    vault = tmp_path / "user-level-vault"
    _write_config(home / ".config" / "loci" / "config.yml", vault)

    result = _run(script, env)

    assert result.returncode == 0, result.stderr
    assert str(vault) in result.stdout
    assert "gdrive" in result.stdout


def test_xdg_config_home_wins_over_the_default(sync_env, tmp_path):
    script, env, home = sync_env
    xdg = tmp_path / "xdg"
    env["XDG_CONFIG_HOME"] = str(xdg)
    _write_config(home / ".config" / "loci" / "config.yml", tmp_path / "wrong")
    _write_config(xdg / "loci" / "config.yml", tmp_path / "xdg-vault")

    result = _run(script, env)

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "xdg-vault") in result.stdout


def test_loci_config_wins_over_everything(sync_env, tmp_path):
    script, env, home = sync_env
    override = tmp_path / "scratch" / "config.yml"
    env["LOCI_CONFIG"] = str(override)
    _write_config(home / ".config" / "loci" / "config.yml", tmp_path / "wrong")
    _write_config(override, tmp_path / "override-vault")

    result = _run(script, env)

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "override-vault") in result.stdout


def test_falls_back_to_the_project_root_config(sync_env, tmp_path):
    """
    A checkout whose server has never run still has config.yml in the project
    root — nothing has migrated it yet, and sync must keep working there.
    """
    script, env, home = sync_env
    _write_config(script.parent.parent / "config.yml", tmp_path / "checkout-vault")

    result = _run(script, env)

    assert result.returncode == 0, result.stderr
    assert str(tmp_path / "checkout-vault") in result.stdout


def test_error_names_the_config_it_looked_for(sync_env, tmp_path):
    """The old message said 'ensure config.yml exists' without saying where."""
    script, env, home = sync_env

    result = _run(script, env)

    assert result.returncode == 1
    assert str(home / ".config" / "loci" / "config.yml") in result.stderr

"""
tests/test_setup_docker.py
Tests for the Docker setup wizard's vault prompt.

setup_docker.py sits at the repo root and runs before anything is installed, so
its vault prompt is a copy of prompt_vault_root() in tools/vault_init.py rather
than a call to it, and these tests are what keep the two wizards agreeing about
what counts as a vault path.

The one thing it does import from the package is skills_install, at step 6.
That makes `uv run setup_docker.py` — which syncs the project first, and is
what the README says to run — a requirement rather than a convention, so main()
checks for it before the first step instead of failing six steps in.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import setup_docker  # noqa: E402  (must follow the sys.path insert)


def test_the_package_check_passes_in_this_environment():
    """The test suite runs with the project synced, which is the same
    environment `uv run setup_docker.py` gives the script."""
    setup_docker.require_loci_package()


def test_a_missing_package_stops_before_anything_is_installed(monkeypatch, capsys):
    """The failure was ordered wrongly, not merely unhandled: Docker installed,
    the vault configured and the container running, and then an ImportError."""
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("loci"):
            raise ImportError(f"no module named {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    monkeypatch.setattr(setup_docker, "ensure_docker", _must_not_run)

    with pytest.raises(SystemExit) as exit_info:
        setup_docker.main()

    assert exit_info.value.code == 1
    assert "uv run setup_docker.py" in capsys.readouterr().err


def _must_not_run(*args, **kwargs):
    raise AssertionError("setup continued past the package check")


def test_ask_vault_path_has_no_default(tmp_path, monkeypatch):
    """Empty input must re-prompt — never fall back to a path in the checkout."""
    target = tmp_path / "vault"
    responses = iter(["", "   ", str(target)])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert setup_docker.ask_vault_path() == target.resolve()


def test_ask_vault_path_never_lands_in_the_checkout(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    responses = iter(["", str(target)])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    result = setup_docker.ask_vault_path()
    assert setup_docker.PROJECT_ROOT not in result.parents


def test_ask_vault_path_rejects_relative_path(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    responses = iter(["some/relative/vault", str(target)])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert setup_docker.ask_vault_path() == target.resolve()


def test_ask_vault_path_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _: "~/loci/knowledge-vault")
    expected = (tmp_path / "loci" / "knowledge-vault").resolve()
    assert setup_docker.ask_vault_path() == expected


def test_ask_vault_path_reprompts_on_unexpandable_tilde(tmp_path, monkeypatch):
    target = tmp_path / "vault"
    responses = iter(["~nosuchuser-typo/vault", str(target)])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert setup_docker.ask_vault_path() == target.resolve()


def test_ask_vault_path_reprompts_when_path_cannot_be_created(tmp_path, monkeypatch):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")
    target = tmp_path / "vault"
    responses = iter([str(blocker / "vault"), str(target)])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert setup_docker.ask_vault_path() == target.resolve()


def test_ask_vault_path_creates_the_directory(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "vault"
    monkeypatch.setattr("builtins.input", lambda _: str(target))
    assert setup_docker.ask_vault_path() == target.resolve()
    assert target.is_dir()


def test_ask_vault_path_exits_on_eof(monkeypatch):
    """Piped stdin must fail with a message, not loop forever on EOF."""
    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    with pytest.raises(SystemExit):
        setup_docker.ask_vault_path()

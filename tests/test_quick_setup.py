"""`loci setup`: skills + registration, agents chosen once."""

import io
import subprocess

import pytest

from loci import clients, quick_setup, skills_install
from loci.clients import CLAUDE, HERMES
from loci.http_server import build_cli, split_command


class Tty(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(clients.shutil, "which", lambda n: f"/bin/{n}")
    calls = []
    state = {"hermes": False}

    def fake(cmd, input=None, capture_output=None, text=None, timeout=None):
        calls.append(cmd)
        if cmd[1:3] == ["config", "get"]:
            return subprocess.CompletedProcess(cmd, 0 if state["hermes"] else 1,
                                               "command: loci-mcp\n" if state["hermes"] else "", "")
        if cmd[1:3] == ["mcp", "add"] and cmd[0].endswith("hermes"):
            state["hermes"] = True
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(clients.subprocess, "run", fake)
    return home, calls


def test_setup_is_a_subcommand():
    assert split_command(["setup", "--target", "all"]) == ("setup", ["--target", "all"])


def test_cli_help_lists_setup():
    assert "setup —" in build_cli().format_help()


def test_target_all_installs_skills_and_registers_both(env):
    home, calls = env
    out = io.StringIO()

    assert quick_setup.run(["--target", "all"], stdout=out) == 0

    assert (home / ".claude" / "skills" / "loci-save" / "SKILL.md").is_file()
    assert (home / ".hermes" / "skills" / "loci-save" / "SKILL.md").is_file()
    assert any(c[1:3] == ["mcp", "add"] and c[0].endswith("claude") for c in calls)
    assert any(c[1:3] == ["mcp", "add"] and c[0].endswith("hermes") for c in calls)
    assert "Done." in out.getvalue() and "point Loci at" in out.getvalue()


def test_the_agent_choice_is_asked_once(env):
    home, _ = env
    (home / ".claude").mkdir()
    (home / ".hermes").mkdir()
    out = Tty()
    stdin = Tty("2\n")

    assert quick_setup.run([], stdin=stdin, stdout=out) == 0

    assert out.getvalue().count("Several agents found") == 1
    assert (home / ".hermes" / "skills" / "loci-save").is_dir()
    assert not (home / ".claude" / "skills").exists()


def test_no_confirmation_prompt_for_the_skill_install(env):
    out = io.StringIO()  # not a terminal: skills would refuse without --yes
    assert quick_setup.run(["--target", "claude"], stdout=out) == 0
    assert "Not a terminal" not in out.getvalue()


def test_several_agents_without_a_terminal_is_refused(env):
    home, calls = env
    (home / ".claude").mkdir()
    (home / ".hermes").mkdir()
    out = io.StringIO()

    assert quick_setup.run([], stdout=out) == 1
    assert "--target" in out.getvalue() and calls == []


def test_a_failed_registration_fails_the_command_but_skills_still_land(env, monkeypatch):
    home, _ = env
    monkeypatch.setattr(clients.shutil, "which", lambda n: None)
    out = io.StringIO()

    assert quick_setup.run(["--target", "claude"], stdout=out) == 1
    assert (home / ".claude" / "skills" / "loci-save").is_dir()
    assert "claude mcp add" in out.getvalue() and "safe to repeat" in out.getvalue()


def test_skill_write_error_does_not_skip_registration(env, monkeypatch):
    _, calls = env
    out = io.StringIO()

    def fail_install(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(skills_install, "run", fail_install)

    assert quick_setup.run(["--target", "claude"], stdout=out) == 1

    assert any(c[1:3] == ["mcp", "add"] for c in calls)
    assert "permission denied" in out.getvalue()
    assert "Finished with problems" in out.getvalue()


def test_setup_is_safe_to_repeat(env):
    out = io.StringIO()
    assert quick_setup.run(["--target", "all"], stdout=out) == 0
    out = io.StringIO()
    assert quick_setup.run(["--target", "all"], stdout=out) == 0
    assert "already registered" in out.getvalue()

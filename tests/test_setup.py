"""
tests/test_setup.py
Tests for the local setup script's skill installer.

`setup.py` is what the skills tell a user to run when the vault is unreachable,
and step 4 replaces whatever sits at ~/.claude/skills/<skill>/ — including the
skill that gave the instruction. It is only safe if the path it links to is
real, so these tests pin that path to the packaged skills directory.

Importing setup.py is possible only because `uv sync` and the vault_init import
live inside sync_and_init_vault() rather than at module scope.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import setup  # noqa: E402  (must follow the sys.path insert)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Path.home() reads HOME on posix, which is what the installer resolves."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_every_installed_skill_exists_in_the_package():
    """The path moved to src/loci/skills/ with the package. A stale one here
    means the installer deletes a working skill and links to nothing."""
    for skill_name in setup.SKILLS:
        assert (setup.SKILLS_DIR / skill_name / "SKILL.md").is_file(), skill_name


def test_install_skill_stubs_writes_a_stub_per_skill(fake_home):
    from loci import skills_install

    setup.install_skill_stubs()

    for skill_name in setup.SKILLS:
        dest = fake_home / ".claude" / "skills" / skill_name
        # A stub, never a link: a symlink into the checkout would hand Claude
        # Code the procedure directly and skip the user's overlay.
        assert not dest.is_symlink()
        assert (dest / "SKILL.md").read_text() == skills_install.packaged_stub(
            setup.SKILLS_DIR / skill_name
        )


def test_install_skill_stubs_is_rerunnable(fake_home):
    setup.install_skill_stubs()
    setup.install_skill_stubs()

    for skill_name in setup.SKILLS:
        assert (fake_home / ".claude" / "skills" / skill_name / "SKILL.md").is_file()


def test_install_skill_stubs_keeps_an_existing_skill_when_the_source_is_gone(
    fake_home, tmp_path, monkeypatch
):
    """
    The failure this guards against is the one the package move caused: the
    installer unlinked the user's skill and pointed it at a directory that no
    longer existed, leaving them worse off than before they ran it.
    """
    monkeypatch.setattr(setup, "SKILLS_DIR", tmp_path / "nowhere")
    existing = fake_home / ".claude" / "skills" / setup.SKILLS[0]
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("# the user's working skill\n")

    setup.install_skill_stubs()

    assert (existing / "SKILL.md").read_text() == "# the user's working skill\n"


def test_desktop_fallback_prints_the_stubs_not_the_procedures(capsys):
    """It reads SKILL.md off the same path the installer uses — when that path
    was stale this printed 'Skill file not found' for every skill. And it
    prints the stub: a pasted procedure would run on its own in Desktop and
    never see the user's overlay."""
    setup.print_desktop_fallback()

    out = capsys.readouterr().out
    assert "Skill file not found" not in out
    for skill_name in setup.SKILLS:
        assert f'loci__read_skill(skill="{skill_name}")' in out
    assert "Ground rule" not in out


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------

def test_install_skill_stubs_can_target_another_agent(fake_home):
    codex_skills = fake_home / ".codex" / "skills"

    setup.install_skill_stubs(codex_skills)

    for skill_name in setup.SKILLS:
        assert (codex_skills / skill_name / "SKILL.md").is_file()
    assert not (fake_home / ".claude").exists()


def test_codex_is_skipped_with_the_manual_command_when_absent(monkeypatch, capsys):
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)

    assert setup.register_mcp_codex() is False
    out = capsys.readouterr().out
    assert "codex mcp add loci" in out
    assert "loci skills --agent codex" in out


def test_codex_registration_runs_the_server_from_the_checkout(monkeypatch):
    calls = []

    class Done:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(setup.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())

    assert setup.register_mcp_codex() is True
    (cmd,) = calls
    assert cmd[:4] == ["/bin/codex", "mcp", "add", "loci"]
    after = cmd[cmd.index("--") + 1:]
    assert after == ["/bin/uv", "run", "--directory", str(setup.PROJECT_ROOT), "loci-mcp"]


def test_a_failed_codex_registration_reports_and_installs_nothing(monkeypatch, capsys):
    class Failed:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(setup.subprocess, "run", lambda cmd, **kw: Failed())

    assert setup.register_mcp_codex() is False
    assert "boom" in capsys.readouterr().out

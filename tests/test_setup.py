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


def test_install_skill_symlink_links_to_the_packaged_skill(fake_home):
    setup.install_skill_symlink()

    for skill_name in setup.SKILLS:
        link = fake_home / ".claude" / "skills" / skill_name
        assert link.is_symlink()
        assert link.resolve() == (setup.SKILLS_DIR / skill_name).resolve()
        # The link resolving is the whole point: a dangling one reads as an
        # installed skill to the client and fails at load.
        assert (link / "SKILL.md").is_file()


def test_install_skill_symlink_is_rerunnable(fake_home):
    setup.install_skill_symlink()
    setup.install_skill_symlink()

    for skill_name in setup.SKILLS:
        link = fake_home / ".claude" / "skills" / skill_name
        assert (link / "SKILL.md").is_file()


def test_install_skill_symlink_keeps_an_existing_skill_when_the_source_is_gone(
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

    setup.install_skill_symlink()

    assert (existing / "SKILL.md").read_text() == "# the user's working skill\n"


def test_desktop_fallback_prints_the_skill_bodies(capsys):
    """It reads SKILL.md off the same path the symlink uses — when that path
    was stale this printed 'Skill file not found' for every skill."""
    setup.print_desktop_fallback()

    out = capsys.readouterr().out
    assert "Skill file not found" not in out
    for skill_name in setup.SKILLS:
        assert skill_name in out

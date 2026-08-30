"""
tests/test_skills_install.py
Tests for `loci skills` — the installer that puts the packaged skills into
~/.claude/skills/.

This is the command that makes an installed wheel usable: there is no checkout
to symlink from, so the skills have to be copied out of the package. The cases
that matter are the ones where it writes over something the user already has,
so most of these are about what it refuses to touch.
"""

import io
from pathlib import Path

import pytest

from loci import skills_install
from loci.http_server import split_command


@pytest.fixture
def skills_root(tmp_path):
    return tmp_path / "skills"


@pytest.fixture
def fake_package(tmp_path):
    """A stand-in for the package's skills/ dir, with versions we control."""
    source = tmp_path / "packaged"
    for name, version in (("loci-save", 23), ("loci-query", 1)):
        skill = source / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\nskill_version: {version}\n---\nbody\n"
        )
    return source


def _install(skills_root, source, version, name="loci-save"):
    """Put a skill at the destination as if an older Loci had installed it."""
    dest = skills_root / name
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(f"---\nskill_version: {version}\n---\nold\n")
    return dest


# ---------------------------------------------------------------------------
# What ships
# ---------------------------------------------------------------------------

def test_every_packaged_skill_is_discovered():
    """All four skills, and never references/ — that directory holds the
    ontology YAML the registries read, and installing it as a skill would put
    a SKILL.md-less directory in front of Claude Code."""
    names = [s.name for s in skills_install.packaged_skills()]

    assert names == ["loci-inbox", "loci-ingest-directory", "loci-query", "loci-save"]
    assert "references" not in names


def test_skills_ship_inside_the_package():
    """Only src/loci/ goes into the wheel. A skills directory outside it exists
    in a checkout and is missing on every machine that installed Loci rather
    than cloning it — which is precisely who this command is for."""
    import loci

    package_root = Path(loci.__file__).parent
    assert skills_install.SKILLS_SOURCE.is_relative_to(package_root)
    assert skills_install.SKILLS_SOURCE.is_dir()


def test_packaged_skills_all_declare_a_version():
    """The install/update decision is made on this number. A skill without one
    is reinstalled every time, which is noise, not breakage — but it means the
    version check inside the SKILL.md cannot work either."""
    for skill in skills_install.packaged_skills():
        assert skills_install.read_skill_version(skill / "SKILL.md") is not None, skill.name


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_missing_skill_is_an_install(skills_root, fake_package):
    statuses = skills_install.plan(skills_root, fake_package)

    assert {s.name: s.action for s in statuses} == {
        "loci-save": skills_install.INSTALL,
        "loci-query": skills_install.INSTALL,
    }


def test_older_installed_version_is_an_update(skills_root, fake_package):
    _install(skills_root, fake_package, version=21)

    by_name = {s.name: s for s in skills_install.plan(skills_root, fake_package)}

    assert by_name["loci-save"].action == skills_install.UPDATE
    assert by_name["loci-save"].installed_version == 21
    assert by_name["loci-save"].packaged_version == 23


def test_matching_version_is_left_alone(skills_root, fake_package):
    dest = _install(skills_root, fake_package, version=23)

    statuses = skills_install.plan(skills_root, fake_package)
    written = skills_install.apply(statuses)

    assert [s.name for s in written] == ["loci-query"]
    assert (dest / "SKILL.md").read_text().endswith("old\n")


def test_installed_version_newer_than_packaged_is_not_clobbered(skills_root, fake_package):
    """Downgrading Loci should not silently roll a skill backwards."""
    dest = _install(skills_root, fake_package, version=99)

    by_name = {s.name: s for s in skills_install.plan(skills_root, fake_package)}
    skills_install.apply(list(by_name.values()))

    assert by_name["loci-save"].action == skills_install.AHEAD
    assert (dest / "SKILL.md").read_text().endswith("old\n")


def test_unparseable_installed_skill_is_reinstalled(skills_root, fake_package):
    dest = skills_root / "loci-save"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("truncated, no frontmatter\n")

    by_name = {s.name: s for s in skills_install.plan(skills_root, fake_package)}

    assert by_name["loci-save"].action == skills_install.UPDATE
    assert by_name["loci-save"].installed_version is None


# ---------------------------------------------------------------------------
# Symlinks — the developer's setup, and the broken one it replaces
# ---------------------------------------------------------------------------

def test_dev_symlink_into_the_package_is_preserved(skills_root, fake_package):
    """A checkout links ~/.claude/skills/loci-save at the repo so edits are
    live. Replacing that with a copy would take the live editing away without
    saying so."""
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(fake_package / "loci-save")

    by_name = {s.name: s for s in skills_install.plan(skills_root, fake_package)}
    skills_install.apply(list(by_name.values()))

    assert by_name["loci-save"].action == skills_install.LINKED
    assert (skills_root / "loci-save").is_symlink()


def test_force_replaces_a_dev_symlink_with_a_copy(skills_root, fake_package):
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(fake_package / "loci-save")

    statuses = skills_install.plan(skills_root, fake_package, force=True)
    skills_install.apply(statuses)

    assert not (skills_root / "loci-save").is_symlink()
    assert (skills_root / "loci-save" / "SKILL.md").is_file()


def test_dangling_symlink_is_repaired(skills_root, fake_package):
    """The state this machine was actually left in by the src/loci/ move: a
    symlink to a path that no longer exists. It reads as an installed skill and
    fails at load, so it has to be replaced, not skipped."""
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(fake_package / "gone")

    skills_install.apply(skills_install.plan(skills_root, fake_package))

    assert not (skills_root / "loci-save").is_symlink()
    assert "skill_version: 23" in (skills_root / "loci-save" / "SKILL.md").read_text()


def test_a_symlink_elsewhere_is_replaced_not_followed(skills_root, tmp_path, fake_package):
    """A link pointing outside the package is someone else's skill, not our
    dev setup. It is replaced — but by unlinking, never by writing through it
    into whatever it pointed at."""
    other = tmp_path / "other" / "loci-save"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("not ours\n")
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(other)

    skills_install.apply(skills_install.plan(skills_root, fake_package))

    assert (other / "SKILL.md").read_text() == "not ours\n"
    assert "skill_version: 23" in (skills_root / "loci-save" / "SKILL.md").read_text()


# ---------------------------------------------------------------------------
# Installing
# ---------------------------------------------------------------------------

def test_install_copies_the_whole_directory(skills_root, fake_package):
    (fake_package / "loci-save" / "reference.md").write_text("supporting file\n")

    skills_install.install_all(skills_root, fake_package)

    assert (skills_root / "loci-save" / "reference.md").read_text() == "supporting file\n"


def test_install_copies_rather_than_links_by_default(skills_root, fake_package):
    """A link into site-packages dangles on the next `uv tool install
    --upgrade`, which is exactly how the machine this replaces got broken."""
    skills_install.install_all(skills_root, fake_package)

    assert not (skills_root / "loci-save").is_symlink()


def test_link_mode_symlinks_back_to_the_source(skills_root, fake_package):
    skills_install.install_all(skills_root, fake_package, link=True)

    link = skills_root / "loci-save"
    assert link.is_symlink()
    assert link.resolve() == (fake_package / "loci-save").resolve()


def test_install_is_rerunnable(skills_root, fake_package):
    skills_install.install_all(skills_root, fake_package)
    skills_install.install_all(skills_root, fake_package, force=True)

    assert (skills_root / "loci-save" / "SKILL.md").is_file()


def test_nothing_packaged_writes_nothing(skills_root, tmp_path):
    """Guards the failure the package move caused once already: an installer
    that deletes the user's skill before discovering it has nothing to put
    back."""
    existing = skills_root / "loci-save"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("the user's working skill\n")

    written = skills_install.install_all(skills_root, tmp_path / "nowhere")

    assert written == []
    assert (existing / "SKILL.md").read_text() == "the user's working skill\n"


# ---------------------------------------------------------------------------
# Skills that are no longer shipped
#
# A rename upstream is the case that bites: the new name installs, the old copy
# stays, and Claude Code loads both. Nothing here may touch a directory this
# installer could not have created.
# ---------------------------------------------------------------------------

def test_a_skill_that_is_no_longer_packaged_is_removed(skills_root, fake_package):
    stale = _install(skills_root, fake_package, 4, name="loci-renamed-away")

    written = skills_install.install_all(skills_root, fake_package)

    assert not stale.exists()
    assert [s.name for s in written if s.action == skills_install.REMOVE] == [
        "loci-renamed-away"
    ]


def test_a_dev_symlink_to_a_skill_that_is_gone_is_removed(skills_root, fake_package):
    """The dangling half of a rename. resolve() still answers for a broken
    link, which is what lets this be recognised as ours at all."""
    skills_root.mkdir(parents=True)
    stale = skills_root / "gone"
    stale.symlink_to(fake_package / "gone")

    skills_install.install_all(skills_root, fake_package)

    assert not stale.is_symlink()


def test_a_users_own_skill_is_left_alone(skills_root, fake_package):
    """~/.claude/skills/ is shared with every other skill the user has. Only
    the packaged prefix and links into the package mark one as ours."""
    theirs = _install(skills_root, fake_package, 1, name="my-own-skill")

    skills_install.install_all(skills_root, fake_package)

    assert (theirs / "SKILL.md").exists()


def test_a_bare_directory_with_the_prefix_is_left_alone(skills_root, fake_package):
    """No SKILL.md means it is not a skill this installer wrote — scratch
    space, a stray checkout — and removing it would be guesswork."""
    skills_root.mkdir(parents=True)
    odd = skills_root / "loci-notes"
    odd.mkdir()
    (odd / "README.md").write_text("mine\n")

    skills_install.install_all(skills_root, fake_package)

    assert odd.exists()


def test_nothing_packaged_removes_nothing(skills_root, tmp_path):
    """The mirror of test_nothing_packaged_writes_nothing. With no packaged
    set to compare against, every installed skill looks orphaned — and the
    installer would delete the lot."""
    existing = _install(skills_root, None, 23)

    written = skills_install.install_all(skills_root, tmp_path / "nowhere")

    assert written == []
    assert existing.exists()


def test_removals_are_reported_in_the_plan(skills_root, fake_package, monkeypatch):
    """It is a deletion in the user's Claude Code config, so it has to appear
    in the table they confirm against."""
    _install(skills_root, fake_package, 4, name="loci-renamed-away")
    monkeypatch.setattr(skills_install, "DEFAULT_SKILLS_ROOT", skills_root)
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    skills_install.run(["--dir", str(skills_root), "--yes"], stdout=out)

    printed = out.getvalue()
    assert "loci-renamed-away" in printed
    assert "1 to remove" in printed


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

def test_run_installs_with_yes(skills_root, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    code = skills_install.run(["--dir", str(skills_root), "--yes"], stdout=out)

    assert code == 0
    assert (skills_root / "loci-save" / "SKILL.md").is_file()
    assert "Restart Claude Code" in out.getvalue()


def test_run_refuses_to_write_without_a_terminal(skills_root, fake_package, monkeypatch):
    """Without --yes and without a tty there is nobody to answer the prompt.
    Assuming yes would replace files in the user's Claude Code config."""
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    code = skills_install.run(["--dir", str(skills_root)], stdin=io.StringIO(), stdout=out)

    assert code == 1
    assert not (skills_root / "loci-save").exists()
    assert "--yes" in out.getvalue()


def test_run_declined_at_the_prompt_writes_nothing(skills_root, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    out = io.StringIO()
    code = skills_install.run(["--dir", str(skills_root)], stdin=Tty("n\n"), stdout=out)

    assert code == 1
    assert not (skills_root / "loci-save").exists()
    assert "Nothing written." in out.getvalue()


def test_run_accepted_at_the_prompt_installs(skills_root, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    code = skills_install.run(["--dir", str(skills_root)], stdin=Tty("y\n"), stdout=io.StringIO())

    assert code == 0
    assert (skills_root / "loci-save" / "SKILL.md").is_file()


def test_run_reports_up_to_date_without_prompting(skills_root, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    skills_install.install_all(skills_root, fake_package)
    out = io.StringIO()

    # No stdin at all: an up-to-date run must not reach the prompt.
    code = skills_install.run(["--dir", str(skills_root)], stdin=None, stdout=out)

    assert code == 0
    assert "Everything is up to date." in out.getvalue()


def test_run_defaults_to_the_packaged_skills(skills_root, monkeypatch):
    """No --dir override of the source: this is the real package, which is what
    a user actually gets."""
    out = io.StringIO()

    code = skills_install.run(["--dir", str(skills_root), "--yes"], stdout=out)

    assert code == 0
    assert (skills_root / "loci-save" / "SKILL.md").is_file()
    assert (skills_root / "loci-inbox" / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# Dispatch from the `loci` entry point
# ---------------------------------------------------------------------------

def test_skills_subcommand_is_split_off_with_its_flags():
    """argparse subparsers dropped the leading flags here — `loci skills
    --yes` arrived as a bare `skills`. The flags must survive the split."""
    assert split_command(["skills", "--yes", "--dir", "/tmp/x"]) == (
        "skills", ["--yes", "--dir", "/tmp/x"]
    )


def test_serving_arguments_are_untouched():
    """Bare `loci` still serves — that is what make run and run_server.sh do."""
    assert split_command([]) == (None, [])
    assert split_command(["--host", "0.0.0.0", "--port", "9000"]) == (
        None, ["--host", "0.0.0.0", "--port", "9000"]
    )

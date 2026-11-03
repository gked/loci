"""
tests/test_skills_install.py
Tests for `loci skills` — the installer that puts a stub for each packaged
skill into ~/.claude/skills/.

A stub, not the skill: the stub calls `read_skill`, and the MCP server serves
the procedure assembled with the user's overlay. A full copy — or a symlink
into the package — would run on its own and never see that overlay, so the
cases that matter most here are the ones about what lands at the destination
and what it refuses to touch.
"""

import io
from pathlib import Path

import pytest

from loci import skills_install
from loci.http_server import split_command


@pytest.fixture
def skills_root(tmp_path):
    return tmp_path / "skills"


FRONTMATTER = "---\nname: {name}\ndescription: >\n  Does {name} things.\n---\n"


def _skill_md(name, procedure="body\n"):
    return FRONTMATTER.format(name=name) + procedure


@pytest.fixture
def fake_package(tmp_path):
    """A stand-in for the package's skills/ dir."""
    source = tmp_path / "packaged"
    for name in ("loci-save", "loci-query"):
        skill = source / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(_skill_md(name))
    return source


def _install(skills_root, text, name="loci-save"):
    """Put a skill at the destination as if an older Loci had installed it."""
    dest = skills_root / name
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(text)
    return dest


def _installed(skills_root, name="loci-save"):
    return (skills_root / name / "SKILL.md").read_text()


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


# ---------------------------------------------------------------------------
# The stub
# ---------------------------------------------------------------------------

def test_stub_keeps_the_frontmatter_verbatim():
    """`name` and `description` are what Claude Code matches on to decide the
    skill applies. The stub has to declare exactly what the packaged skill
    declares, or the trigger phrases in the skill's description stop working."""
    text = _skill_md("loci-save", "## Step 1\nDo the thing.\n")

    stub = skills_install.stub("loci-save", text)

    assert stub.startswith(FRONTMATTER.format(name="loci-save"))


def test_stub_carries_none_of_the_procedure():
    """The whole point. A procedure in the local copy is a procedure that
    runs locally, and the user's overlay lives on the other side of read_skill."""
    stub = skills_install.stub("loci-save", _skill_md("loci-save", "## Step 1\nDo the thing.\n"))

    assert "Do the thing" not in stub
    assert 'loci__read_skill(skill="loci-save")' in stub


def test_stub_tells_the_model_what_to_do_when_the_server_is_missing():
    """The stub is the only thing Claude Code has when the MCP server is not
    connected, so the failure path has to live in it rather than in the
    procedure the server would have served."""
    stub = skills_install.stub("loci-query", _skill_md("loci-query"))

    assert "error text verbatim" in stub
    assert "check their MCP client config" in stub


@pytest.mark.parametrize("skill", skills_install.packaged_skills(), ids=lambda p: p.name)
def test_every_packaged_skill_produces_a_stub_that_names_itself(skill):
    stub = skills_install.packaged_stub(skill)

    assert f"name: {skill.name}" in stub
    assert f'loci__read_skill(skill="{skill.name}")' in stub


# ---------------------------------------------------------------------------
# Deciding what to do
# ---------------------------------------------------------------------------

def test_missing_skill_is_an_install(skills_root, fake_package):
    plan = skills_install.plan(skills_root, fake_package)

    assert {s.name: s.action for s in plan} == {
        "loci-save": skills_install.INSTALL,
        "loci-query": skills_install.INSTALL,
    }


def test_a_full_copy_from_an_older_loci_is_an_update(skills_root, fake_package):
    """What every install before the stubs left behind: the whole procedure,
    version check and all. It has to be replaced — left in place it runs on
    its own and never reaches the overlay."""
    _install(skills_root, "---\nname: loci-save\nskill_version: 23\n---\nold procedure\n")

    plan = skills_install.plan(skills_root, fake_package)

    assert [s.action for s in plan if s.name == "loci-save"] == [skills_install.UPDATE]


def test_an_identical_stub_is_left_alone(skills_root, fake_package):
    skills_install.install_all(skills_root, fake_package)

    plan = skills_install.plan(skills_root, fake_package)

    assert {s.action for s in plan} == {skills_install.CURRENT}


def test_a_reworded_description_is_an_update(skills_root, fake_package):
    """The one kind of packaged change that reaches the stub."""
    skills_install.install_all(skills_root, fake_package)
    (fake_package / "loci-save" / "SKILL.md").write_text(
        "---\nname: loci-save\ndescription: now also triggers on 'stash this'\n---\nbody\n"
    )

    plan = skills_install.plan(skills_root, fake_package)

    assert [s.action for s in plan if s.name == "loci-save"] == [skills_install.UPDATE]
    assert [s.action for s in plan if s.name == "loci-query"] == [skills_install.CURRENT]


def test_a_procedure_edit_alone_is_not_an_update(skills_root, fake_package):
    """The server reads the procedure live; nothing installed changes."""
    skills_install.install_all(skills_root, fake_package)
    (fake_package / "loci-save" / "SKILL.md").write_text(_skill_md("loci-save", "rewritten\n"))

    plan = skills_install.plan(skills_root, fake_package)

    assert [s.action for s in plan if s.name == "loci-save"] == [skills_install.CURRENT]


def test_a_dev_symlink_into_the_package_is_replaced(skills_root, fake_package):
    """The old checkout setup. Left in place it hands Claude Code the procedure
    directly and the overlay is never seen — so it goes, unconditionally."""
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(fake_package / "loci-save")

    written = skills_install.install_all(skills_root, fake_package)

    dest = skills_root / "loci-save"
    assert [s.action for s in written if s.name == "loci-save"] == [skills_install.UPDATE]
    assert not dest.is_symlink()
    assert _installed(skills_root) == skills_install.packaged_stub(fake_package / "loci-save")


def test_dangling_symlink_is_repaired(skills_root, fake_package):
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(fake_package / "does-not-exist")

    skills_install.install_all(skills_root, fake_package)

    assert (skills_root / "loci-save" / "SKILL.md").is_file()
    assert not (skills_root / "loci-save").is_symlink()


def test_a_symlink_elsewhere_is_replaced_not_followed(skills_root, tmp_path, fake_package):
    """Replacing the link must not write through it into whatever it points at."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "SKILL.md").write_text("theirs\n")
    skills_root.mkdir(parents=True)
    (skills_root / "loci-save").symlink_to(elsewhere)

    skills_install.install_all(skills_root, fake_package)

    assert (elsewhere / "SKILL.md").read_text() == "theirs\n"
    assert not (skills_root / "loci-save").is_symlink()


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def test_install_writes_the_stub_and_only_the_stub(skills_root, fake_package):
    (fake_package / "loci-save" / "extra.md").write_text("reference\n")

    skills_install.install_all(skills_root, fake_package)

    dest = skills_root / "loci-save"
    assert sorted(p.name for p in dest.iterdir()) == ["SKILL.md"]
    assert _installed(skills_root) == skills_install.packaged_stub(fake_package / "loci-save")


def test_install_replaces_leftovers_from_a_whole_directory_copy(skills_root, fake_package):
    """Older installs copied the skill directory wholesale."""
    dest = _install(skills_root, "old\n")
    (dest / "reference.md").write_text("stale\n")

    skills_install.install_all(skills_root, fake_package)

    assert sorted(p.name for p in dest.iterdir()) == ["SKILL.md"]


def test_install_is_rerunnable(skills_root, fake_package):
    skills_install.install_all(skills_root, fake_package)
    written = skills_install.install_all(skills_root, fake_package)

    assert written == []
    assert (skills_root / "loci-save" / "SKILL.md").is_file()


def test_nothing_packaged_writes_nothing(skills_root, tmp_path):
    """Guards the failure the package move caused once already: an installer
    that deletes the user's skill before discovering it has nothing to put
    back."""
    existing = _install(skills_root, "the user's working skill\n")

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
    stale = _install(skills_root, "old\n", name="loci-renamed-away")

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
    theirs = _install(skills_root, "mine\n", name="my-own-skill")

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
    existing = _install(skills_root, "old\n")

    written = skills_install.install_all(skills_root, tmp_path / "nowhere")

    assert written == []
    assert existing.exists()


def test_removals_are_reported_in_the_plan(skills_root, fake_package, monkeypatch):
    """It is a deletion in the user's Claude Code config, so it has to appear
    in the table they confirm against."""
    _install(skills_root, "old\n", name="loci-renamed-away")
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
    # --dir can be any agent's folder, so the message cannot name one.
    assert "Restart your agent" in out.getvalue()


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


def test_run_has_no_way_to_ask_for_symlinks(skills_root, fake_package, monkeypatch):
    """`--link` and `--force` are gone on purpose: a link into the package is
    the one install this command must never produce, and there is nothing a
    force could override now that the decision is a byte comparison."""
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)

    with pytest.raises(SystemExit):
        skills_install.run(["--dir", str(skills_root), "--yes", "--link"])
    with pytest.raises(SystemExit):
        skills_install.run(["--dir", str(skills_root), "--yes", "--force"])


def test_run_defaults_to_the_packaged_skills(skills_root, monkeypatch):
    """No --dir override of the source: this is the real package, which is what
    a user actually gets."""
    out = io.StringIO()

    code = skills_install.run(["--dir", str(skills_root), "--yes"], stdout=out)

    assert code == 0
    assert (skills_root / "loci-save" / "SKILL.md").is_file()
    assert (skills_root / "loci-inbox" / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# Agents other than Claude Code
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    # Bound at import time from the real home; point it at the fake one.
    monkeypatch.setattr(skills_install, "DEFAULT_SKILLS_ROOT", home / ".claude" / "skills")
    return home


def test_codex_reads_skills_from_its_home(fake_home):
    assert skills_install.agent_skills_root("codex") == fake_home / ".codex" / "skills"


def test_codex_home_moves_the_codex_skills_dir(fake_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    assert skills_install.agent_skills_root("codex") == tmp_path / "elsewhere" / "skills"


def test_claude_is_the_default_agent(fake_home):
    assert skills_install.agent_skills_root("claude") == fake_home / ".claude" / "skills"


def test_an_unknown_agent_is_refused():
    with pytest.raises(ValueError):
        skills_install.agent_skills_root("notepad")


def test_run_without_a_target_still_installs_for_claude_code(fake_home, fake_package, monkeypatch):
    """No flag keeps the old behaviour: the git hooks and every doc rely on it."""
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    code = skills_install.run(["--yes"], stdout=out)

    assert code == 0
    assert (fake_home / ".claude" / "skills" / "loci-save" / "SKILL.md").is_file()
    assert not (fake_home / ".codex").exists()
    assert "Restart Claude Code" in out.getvalue()


def test_run_installs_for_codex(fake_home, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    code = skills_install.run(["--agent", "codex", "--yes"], stdout=out)

    assert code == 0
    assert (fake_home / ".codex" / "skills" / "loci-save" / "SKILL.md").is_file()
    assert not (fake_home / ".claude").exists()
    assert "Restart Codex" in out.getvalue()


def test_run_installs_for_several_agents_in_one_go(fake_home, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    out = io.StringIO()

    code = skills_install.run(
        ["--agent", "claude", "--agent", "codex", "--agent", "codex", "--yes"], stdout=out
    )

    assert code == 0
    for agent_dir in (".claude", ".codex"):
        assert (fake_home / agent_dir / "skills" / "loci-query" / "SKILL.md").is_file()
    # A repeated --agent is one target, not two passes over the same folder.
    assert out.getvalue().count("Restart Codex") == 1


def test_run_only_restarts_the_agents_it_changed(fake_home, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    skills_install.install_all(fake_home / ".claude" / "skills", fake_package)
    out = io.StringIO()

    code = skills_install.run(["--agent", "claude", "--agent", "codex", "--yes"], stdout=out)

    assert code == 0
    assert "Restart Codex" in out.getvalue()
    assert "Restart Claude Code" not in out.getvalue()


def test_agent_and_dir_cannot_be_combined(skills_root, fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    with pytest.raises(SystemExit):
        skills_install.run(["--agent", "codex", "--dir", str(skills_root), "--yes"])


def test_an_unknown_agent_name_is_a_usage_error(fake_package, monkeypatch):
    monkeypatch.setattr(skills_install, "SKILLS_SOURCE", fake_package)
    with pytest.raises(SystemExit):
        skills_install.run(["--agent", "notepad", "--yes"])


def test_stub_explains_the_tool_name_differs_between_agents():
    """Claude Code lists the tool as mcp__loci__read_skill, other agents differently;
    the stub must not read as if only one client exists."""
    stub = skills_install.stub("loci-save", _skill_md("loci-save"))
    assert "`read_skill` tool of the `loci` MCP server" in stub
    assert "Claude Code / Claude Desktop" not in stub


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

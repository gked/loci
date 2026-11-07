"""
tests/test_clients.py
Which agents Loci targets, how the choice is made, and how each is registered.

The rule under test: detection offers, it never enrols. Several agents on one
machine means the user decides (or passes --target); the one exception is an
agent that already has Loci stubs, which is refreshed rather than enrolled.
"""

import io
import subprocess

import pytest

from loci import clients, skills_install
from loci.clients import CLAUDE, HERMES, TargetError


class Tty(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    # No real `claude` / `hermes` binary may make a client look detected.
    monkeypatch.setattr(clients.shutil, "which", lambda name: None)
    return home


def _stub_dir(root, name="loci-save"):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\n")


# -- paths -------------------------------------------------------------------

def test_hermes_skills_root_follows_hermes_home(fake_home, monkeypatch, tmp_path):
    assert HERMES.skills_root() == fake_home / ".hermes" / "skills"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))
    assert HERMES.skills_root() == tmp_path / "profile" / "skills"


def test_detection_is_by_home_dir_or_binary(fake_home, monkeypatch):
    assert clients.detected() == []
    (fake_home / ".hermes").mkdir()
    assert clients.detected() == [HERMES]
    monkeypatch.setattr(clients.shutil, "which", lambda n: "/bin/claude" if n == "claude" else None)
    assert clients.detected() == [CLAUDE, HERMES]


# -- stubs -------------------------------------------------------------------

def test_hermes_stub_uses_hermes_tool_name_and_keeps_frontmatter():
    text = "---\nname: loci-save\ndescription: >\n  Saves.\n---\nbody\n"
    stub = skills_install.stub("loci-save", text, HERMES)

    assert stub.startswith("---\nname: loci-save\ndescription: >\n  Saves.\n---\n")
    assert 'mcp_loci_read_skill(skill="loci-save")' in stub
    assert "loci__read_skill" not in stub
    assert "/reload-mcp" in stub
    assert "body" not in stub


def test_claude_stub_is_unchanged_by_the_client_split():
    stub = skills_install.stub("loci-save", "---\nname: loci-save\n---\n")
    assert 'loci__read_skill(skill="loci-save")' in stub
    assert "restart\nClaude Code / Claude Desktop." in stub


def test_installing_for_hermes_writes_hermes_stubs_under_hermes_home(fake_home):
    skills_install.install_all(HERMES.skills_root(), client=HERMES)

    text = (HERMES.skills_root() / "loci-save" / "SKILL.md").read_text()
    assert "mcp_loci_read_skill" in text


def test_orphan_removal_in_a_hermes_tree_leaves_other_skills_alone(fake_home):
    root = HERMES.skills_root()
    _stub_dir(root, "loci-renamed-away")
    _stub_dir(root, "arxiv")  # a Hermes bundled skill: no loci- prefix

    skills_install.install_all(root, client=HERMES)

    assert not (root / "loci-renamed-away").exists()
    assert (root / "arxiv" / "SKILL.md").is_file()


# -- resolving targets -------------------------------------------------------

def test_explicit_target_skips_detection(fake_home):
    assert clients.resolve_targets("hermes") == [HERMES]
    assert clients.resolve_targets("claude,hermes") == [CLAUDE, HERMES]
    assert clients.resolve_targets("all") == [CLAUDE, HERMES]


def test_unknown_target_is_an_error(fake_home):
    with pytest.raises(TargetError, match="Unknown target"):
        clients.resolve_targets("codex")


def test_nothing_found_says_where_it_looked(fake_home):
    with pytest.raises(TargetError, match="No supported agent"):
        clients.resolve_targets(None, io.StringIO(), io.StringIO())


def test_one_detected_agent_is_used(fake_home):
    (fake_home / ".hermes").mkdir()
    assert clients.resolve_targets(None, io.StringIO(), io.StringIO()) == [HERMES]


def test_several_agents_without_a_terminal_is_refused(fake_home):
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    with pytest.raises(TargetError, match="--target"):
        clients.resolve_targets(None, io.StringIO(), io.StringIO())


def test_several_agents_on_a_terminal_asks_and_obeys(fake_home):
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    out = io.StringIO()

    assert clients.resolve_targets(None, Tty("2\n"), out) == [HERMES]
    assert "Claude Code" in out.getvalue() and "Hermes" in out.getvalue()
    assert clients.resolve_targets(None, Tty("all\n"), io.StringIO()) == [CLAUDE, HERMES]


def test_the_prompt_preselects_only_agents_that_already_have_loci(fake_home):
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    _stub_dir(CLAUDE.skills_root())

    # Enter alone keeps the existing install and does not enrol Hermes.
    assert clients.resolve_targets(None, Tty("\n"), io.StringIO()) == [CLAUDE]


def test_empty_answer_with_nothing_installed_selects_nothing(fake_home):
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    with pytest.raises(TargetError, match="Nothing selected"):
        clients.resolve_targets(None, Tty("\n"), io.StringIO())


def test_non_interactive_refreshes_installed_agents_without_enrolling_others(fake_home):
    """What the git hooks and `--yes` rely on."""
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    _stub_dir(CLAUDE.skills_root())

    assert clients.resolve_targets(None, io.StringIO(), io.StringIO()) == [CLAUDE]


# -- loci skills --target ----------------------------------------------------

def test_run_with_target_hermes_installs_only_there(fake_home):
    (fake_home / ".claude").mkdir()
    out = io.StringIO()

    code = skills_install.run(["--target", "hermes", "--yes"], stdout=out)

    assert code == 0
    assert (HERMES.skills_root() / "loci-save" / "SKILL.md").is_file()
    assert not CLAUDE.skills_root().exists()
    assert "Restart Hermes" in out.getvalue()


def test_run_with_several_agents_and_no_target_refuses(fake_home):
    (fake_home / ".hermes").mkdir()
    (fake_home / ".claude").mkdir()
    out = io.StringIO()

    assert skills_install.run(["--yes"], stdin=io.StringIO(), stdout=out) == 1
    assert "--target" in out.getvalue()
    assert not HERMES.skills_root().exists()


# -- startup refresh ---------------------------------------------------------

def test_refresh_updates_installed_agents_and_skips_the_rest(fake_home):
    (fake_home / ".hermes").mkdir()
    _stub_dir(CLAUDE.skills_root())  # stale: wrong content

    written = skills_install.refresh_installed()

    assert {w.client.key for w in written} == {"claude"}
    assert "loci__read_skill" in (CLAUDE.skills_root() / "loci-save" / "SKILL.md").read_text()
    assert not HERMES.skills_root().exists()


def test_refresh_is_a_noop_when_current(fake_home):
    skills_install.install_all(CLAUDE.skills_root(), client=CLAUDE)
    assert skills_install.refresh_installed() == []


def test_refresh_can_be_turned_off(fake_home, monkeypatch):
    _stub_dir(CLAUDE.skills_root())
    monkeypatch.setenv("LOCI_SKIP_SKILL_REFRESH", "1")
    assert skills_install.refresh_installed() == []


def test_refresh_survives_an_unwritable_skills_dir(fake_home, monkeypatch):
    _stub_dir(CLAUDE.skills_root())

    def boom(*a, **k):
        raise PermissionError("read-only")

    monkeypatch.setattr(skills_install, "install_all", boom)
    assert skills_install.refresh_installed() == []


# -- MCP registration --------------------------------------------------------

class FakeRun:
    """Stands in for subprocess.run and records the calls."""

    def __init__(self, registered=False):
        self.calls = []
        self.registered = registered

    def __call__(self, cmd, input=None, capture_output=None, text=None):
        self.calls.append((cmd, input))
        if cmd[1:3] == ["config", "get"]:
            out = "command: loci-mcp\n" if self.registered else ""
            return subprocess.CompletedProcess(cmd, 0 if self.registered else 1, out, "")
        if cmd[1:3] == ["mcp", "add"]:
            self.registered = True
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def bins(monkeypatch):
    monkeypatch.setattr(clients.shutil, "which", lambda n: f"/bin/{n}")


def test_hermes_registration_runs_mcp_add_and_answers_its_prompts(bins, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(clients.subprocess, "run", fake)

    ok, _ = clients.register_mcp(HERMES)

    assert ok
    add = [c for c in fake.calls if c[0][1:3] == ["mcp", "add"]]
    assert add[0][0] == ["/bin/hermes", "mcp", "add", "loci", "--command", "loci-mcp"]
    assert add[0][1] == "y\ny\n"


def test_hermes_registration_passes_args_for_a_checkout(bins, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(clients.subprocess, "run", fake)

    clients.register_mcp(HERMES, "uv", ["run", "--directory", "/x", "loci-mcp"])

    add = [c for c in fake.calls if c[0][1:3] == ["mcp", "add"]][0][0]
    assert add[-7:] == ["--command", "uv", "--args", "run", "--directory", "/x", "loci-mcp"]


def test_hermes_registration_leaves_an_existing_entry_alone(bins, monkeypatch):
    fake = FakeRun(registered=True)
    monkeypatch.setattr(clients.subprocess, "run", fake)

    ok, message = clients.register_mcp(HERMES)

    assert ok and "already" in message
    assert not any(c[0][1:3] == ["mcp", "add"] for c in fake.calls)


def test_hermes_registration_reports_a_silent_cancel(bins, monkeypatch):
    """`hermes mcp add` exits 0 when it cancels, so success is read from config."""
    def cancelled(cmd, input=None, capture_output=None, text=None):
        return subprocess.CompletedProcess(cmd, 1 if cmd[1:3] == ["config", "get"] else 0, "", "")

    monkeypatch.setattr(clients.subprocess, "run", cancelled)

    ok, message = clients.register_mcp(HERMES)

    assert not ok and "hermes mcp add loci --command loci-mcp" in message


def test_claude_registration_uses_user_scope(bins, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(clients.subprocess, "run", fake)

    ok, _ = clients.register_mcp(CLAUDE)

    assert ok
    assert fake.calls[0][0] == ["/bin/claude", "mcp", "add", "--scope", "user", "loci", "loci-mcp"]


def test_missing_binary_prints_the_manual_command(fake_home):
    ok, message = clients.register_mcp(HERMES)
    assert not ok and "hermes mcp add loci --command loci-mcp" in message


def test_register_subcommand_is_split_off():
    from loci.http_server import split_command

    assert split_command(["register", "--target", "hermes"]) == ("register", ["--target", "hermes"])


def test_run_register_target_hermes(bins, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(clients.subprocess, "run", fake)
    out = io.StringIO()

    assert clients.run_register(["--target", "hermes"], stdout=out) == 0
    assert "Hermes: registered" in out.getvalue()

"""
tests/test_git_hooks.py
The post-checkout / post-merge hooks that reinstall the Loci skill stubs.

The stub in ~/.claude/skills/ calls read_skill, and the server reads the
checkout's SKILL.md live, so an edit needs no sync step. What a stub cannot do
is create itself: a skill directory someone else added arrives with a pull and
nothing in ~/.claude/skills/ names it, so Claude Code never sees the skill.
These hooks close that gap.

The rule that matters most is the one about failure. These run attached to
`git checkout` and `git pull`, and neither may be broken by a skill install
going wrong — every path here has to exit 0.
"""

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOKS_DIR = REPO_ROOT / ".githooks"


@dataclass
class Sandbox:
    """A repo with the hooks installed, plus where the fake `uv` logs calls."""

    path: Path
    calls: Path
    bin_dir: Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=repo, capture_output=True, text=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A repo with the hooks installed and a fake `uv` that records its calls.

    The fake is what makes the assertions possible: the real hook shells out to
    `uv run loci skills`, and this suite must not touch ~/.claude/skills.
    """
    repo = tmp_path / "repo"
    (repo / "src" / "loci" / "skills" / "loci-save").mkdir(parents=True)
    (repo / "src" / "loci" / "skills" / "loci-save" / "SKILL.md").write_text("v1\n")
    (repo / "other.txt").write_text("unrelated\n")

    hooks = repo / ".githooks"
    shutil.copytree(HOOKS_DIR, hooks)

    # Not "main": this repo's own pre-commit hook refuses commits on a
    # protected branch, and core.hooksPath below turns it on for the sandbox
    # too — every commit these tests make would be blocked.
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "core.hooksPath", ".githooks")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "first")

    # A `uv` that appends its arguments to a file instead of running anything.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "uv-calls.txt"
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IEXEC)

    return Sandbox(path=repo, calls=calls, bin_dir=bin_dir)


def _env(repo, **extra):
    return {
        **os.environ,
        "PATH": f"{repo.bin_dir}:{os.environ['PATH']}",
        **extra,
    }


def _run_hook(repo, name, *args, **extra_env):
    return subprocess.run(
        [str(repo.path / ".githooks" / name), *args],
        cwd=repo.path, capture_output=True, text=True, env=_env(repo, **extra_env),
    )


def _calls(repo) -> str:
    return repo.calls.read_text() if repo.calls.exists() else ""


def _change_skill(repo, text="v2\n"):
    (repo.path / "src" / "loci" / "skills" / "loci-save" / "SKILL.md").write_text(text)
    _git(repo.path, "add", ".")
    _git(repo.path, "commit", "-qm", "skill change")


def _change_other(repo):
    (repo.path / "other.txt").write_text("changed\n")
    _git(repo.path, "add", ".")
    _git(repo.path, "commit", "-qm", "unrelated change")


def _head(repo) -> str:
    return _git(repo.path, "rev-parse", "HEAD").stdout.strip()


# ---------------------------------------------------------------------------
# When it runs
# ---------------------------------------------------------------------------

def test_a_skill_change_triggers_a_reinstall(repo):
    before = _head(repo)
    _change_skill(repo)
    after = _head(repo)

    result = _run_hook(repo, "post-checkout", before, after, "1")

    assert result.returncode == 0
    assert "loci skills --yes" in _calls(repo)


def test_the_reinstall_writes_stubs_not_links(repo):
    """A symlink into the checkout would hand Claude Code the procedure
    directly, bypassing the server-assembled skill and the user's overlay
    with it — the exact failure the stubs exist to prevent."""
    before = _head(repo)
    _change_skill(repo)

    _run_hook(repo, "post-checkout", before, _head(repo), "1")

    assert "--link" not in _calls(repo)
    assert "--force" not in _calls(repo)


def test_an_unrelated_change_does_not(repo):
    """Every branch switch fires this hook. Running a skill install on each one
    would put it on the critical path of a command people run constantly."""
    before = _head(repo)
    _change_other(repo)
    after = _head(repo)

    _run_hook(repo, "post-checkout", before, after, "1")

    assert _calls(repo) == ""


def test_a_file_checkout_does_not(repo):
    """`git checkout -- path` passes 0 as the third argument. HEAD has not
    moved, so there is nothing to compare and nothing to reinstall."""
    before = _head(repo)
    _change_skill(repo)
    after = _head(repo)

    _run_hook(repo, "post-checkout", before, after, "0")

    assert _calls(repo) == ""


def test_post_merge_compares_against_orig_head(repo):
    """A merge leaves the pre-merge commit in ORIG_HEAD; that is the only
    handle the hook gets on what the pull brought in."""
    before = _head(repo)
    _change_skill(repo)
    _git(repo.path, "update-ref", "ORIG_HEAD", before)

    result = _run_hook(repo, "post-merge", "0")

    assert result.returncode == 0
    assert "loci skills --yes" in _calls(repo)


def test_post_merge_is_quiet_when_no_skill_moved(repo):
    before = _head(repo)
    _change_other(repo)
    _git(repo.path, "update-ref", "ORIG_HEAD", before)

    _run_hook(repo, "post-merge", "0")

    assert _calls(repo) == ""


# ---------------------------------------------------------------------------
# It must never break the git command it is attached to
# ---------------------------------------------------------------------------

def test_the_escape_hatch_skips_it(repo):
    before = _head(repo)
    _change_skill(repo)
    after = _head(repo)

    result = _run_hook(repo, "post-checkout", before, after, "1", LOCI_SKIP_SKILL_INSTALL="1")

    assert result.returncode == 0
    assert _calls(repo) == ""


def test_a_failing_install_does_not_fail_the_checkout(repo):
    """The trade this makes explicitly: a stub one install behind is better
    than a checkout that aborts."""
    fake_uv = repo.bin_dir / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 1\n")

    before = _head(repo)
    _change_skill(repo)
    after = _head(repo)

    result = _run_hook(repo, "post-checkout", before, after, "1")

    assert result.returncode == 0
    assert "make skills" in result.stderr


def test_no_uv_on_path_is_not_an_error(repo):
    """A GUI client's PATH often misses uv — the same trap pre-push documents."""
    (repo.bin_dir / "uv").unlink()

    before = _head(repo)
    _change_skill(repo)
    after = _head(repo)

    result = subprocess.run(
        [str(repo.path / ".githooks" / "post-checkout"), before, after, "1"],
        cwd=repo.path, capture_output=True, text=True,
        # A PATH with no uv on it — but still enough to find bash and git, or
        # this would test the shebang failing rather than the missing uv.
        env={**os.environ, "PATH": f"{repo.bin_dir}:/usr/bin:/bin"},
    )

    assert result.returncode == 0


def test_an_unresolvable_rev_is_not_an_error(repo):
    """ORIG_HEAD does not exist in a fresh clone that has never merged."""
    result = _run_hook(repo, "post-merge", "0")

    assert result.returncode == 0
    assert _calls(repo) == ""


# ---------------------------------------------------------------------------
# The hook and the Makefile have to name the same thing
# ---------------------------------------------------------------------------

def test_the_recovery_command_the_hook_names_exists():
    """The failure path tells the user to run `make skills`. A target that
    does not exist would send them somewhere with no way back."""
    assert "make skills" in (HOOKS_DIR / "_install_skills.sh").read_text()

    # And it has to do what the hook did, or the recovery leaves the developer
    # exactly where the failure did.
    makefile = (REPO_ROOT / "Makefile").read_text()
    recipe = makefile.split("\nskills:", 1)[1].split("\n\n", 1)[0]
    assert "loci skills" in recipe
    assert "--link" not in makefile, "no target may install symlinks — see skills_install.py"


def test_the_hooks_are_executable():
    """core.hooksPath runs the file directly; a non-executable hook is skipped
    silently, which looks exactly like a hook that decided to do nothing."""
    for name in ("post-checkout", "post-merge", "_install_skills.sh"):
        assert os.access(HOOKS_DIR / name, os.X_OK), name

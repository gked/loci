"""
tests/test_conftest_git_env.py
The no_inherited_git_env guard in conftest — a test's git never leaves tmp_path.

git exports GIT_DIR to a hook fired from a linked worktree, and the pre-push
hook runs this suite. Without the guard, every git a test runs — building a
throwaway repo, or through release_notes — acts on the real repository.
"""
import os
import subprocess


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_no_git_variable_reaches_a_test():
    assert [k for k in os.environ if k.startswith("GIT_")] == []


def test_the_guard_drops_a_git_dir_the_process_was_given(tmp_path, monkeypatch, request):
    # Not `from conftest import`: with the whole tree collected that name can
    # resolve to tests/e2e/conftest.py. Ask pytest for the fixture's function.
    guard = request._fixturemanager.getfixturedefs("no_inherited_git_env", request.node)[0].func

    decoy = tmp_path / "decoy"
    _git(tmp_path, "init", "-q", "-b", "main", str(decoy))
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))

    # The autouse instance ran before the variables were planted; run the
    # guard again over an environment shaped like a worktree hook's.
    guard(monkeypatch)

    assert "GIT_DIR" not in os.environ and "GIT_WORK_TREE" not in os.environ
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert (repo / ".git").is_dir()
    assert _git(decoy, "rev-parse", "--is-bare-repository").stdout.strip() == "false"

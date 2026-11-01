"""
tests/test_release.py
The release pipeline: scripts/release.py and scripts/release_notes.py.

Two things here are worth more than the rest. `check_tag` is the guard that
lets the version stay a human decision — it is what catches a tag pushed
before its bump PR merged, and without it a wheel can be published claiming a
version nothing else in the repo agrees with. And the upgrade section is the
only part of a release's notes that asks the reader to do something, so it has
to appear when a skill or the meta files moved, and stay out of the way when
they did not.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import release  # noqa: E402  (must follow sys.path insert)
from scripts import release_notes  # noqa: E402
from scripts.release import (  # noqa: E402
    ReleaseError,
    bump_version,
    check_tag,
    read_version,
    set_version,
    tag_name,
    version_from_tag,
)

PYPROJECT = '''[project]
name = "loci"
version = "0.4.2"
dependencies = ["mcp[cli]>=1.0,<2"]

[tool.something]
version = "9.9.9"
'''


# ---------------------------------------------------------------------------
# Version arithmetic
# ---------------------------------------------------------------------------

def test_reads_the_project_version():
    assert read_version(PYPROJECT) == "0.4.2"


def test_reads_the_real_pyproject():
    """The regex has to match the file it will actually be pointed at."""
    assert read_version((REPO_ROOT / "pyproject.toml").read_text())


def test_missing_version_line_is_an_error():
    with pytest.raises(ReleaseError, match="no `version"):
        read_version('[project]\nname = "loci"\n')


@pytest.mark.parametrize(
    "current,part,expected",
    [
        ("0.4.2", "patch", "0.4.3"),
        ("0.4.2", "minor", "0.5.0"),
        ("0.4.2", "major", "1.0.0"),
        ("0.9.9", "minor", "0.10.0"),
        ("1.2.3", "major", "2.0.0"),
    ],
)
def test_bump(current, part, expected):
    assert bump_version(current, part) == expected


def test_minor_and_major_reset_what_is_below_them():
    """A minor that kept the old patch number would produce 0.5.2 — a version
    that reads as the third patch of a release nobody ever made."""
    assert bump_version("0.4.2", "minor").endswith(".0")
    assert bump_version("0.4.2", "major") == "1.0.0"


def test_unknown_bump_is_an_error():
    with pytest.raises(ReleaseError, match="unknown bump"):
        bump_version("0.4.2", "huge")


def test_set_version_replaces_only_the_project_version():
    """There is a second `version = ` line in the file. Rewriting it too would
    quietly edit an unrelated table."""
    updated = set_version(PYPROJECT, "0.5.0")

    assert 'version = "0.5.0"' in updated
    assert 'version = "9.9.9"' in updated
    assert 'version = "0.4.2"' not in updated


def test_set_version_leaves_dependency_pins_alone():
    assert 'mcp[cli]>=1.0,<2' in set_version(PYPROJECT, "1.0.0")


# ---------------------------------------------------------------------------
# The tag guard
# ---------------------------------------------------------------------------

def test_tag_name_round_trips():
    assert version_from_tag(tag_name("0.4.2")) == "0.4.2"


@pytest.mark.parametrize("tag", ["0.4.2", "v0.4", "release-0.4.2", "v0.4.2-rc1", ""])
def test_non_release_tags_are_rejected(tag):
    with pytest.raises(ReleaseError, match="not a release tag"):
        version_from_tag(tag)


def test_check_tag_accepts_a_matching_tag():
    assert check_tag("v0.4.2", PYPROJECT) == "0.4.2"


def test_check_tag_rejects_a_mismatch_and_says_why():
    """The realistic mistake: tagging main before the bump PR has merged."""
    with pytest.raises(ReleaseError, match="has probably not merged"):
        check_tag("v0.5.0", PYPROJECT)


# ---------------------------------------------------------------------------
# The upgrade section
# ---------------------------------------------------------------------------

FM_A = "---\nname: loci-save\ndescription: save things\n---\n"
FM_B = "---\nname: loci-save\ndescription: save things, and remember things\n---\n"
FM_Q = "---\nname: loci-query\ndescription: ask things\n---\n"


def _snap(meta=None, **skills):
    return release_notes.Snapshot(meta_version=meta, skills=skills)


def test_nothing_moved_produces_no_section():
    """Most releases touch neither. An empty string is what keeps a pointless
    'Upgrading: nothing to do' heading off every set of notes."""
    before = _snap(meta=9, **{"loci-save": FM_A})
    assert release_notes.upgrade_section(before, before) == ""


def test_meta_bump_says_it_reseeds_itself():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": FM_A}),
        _snap(meta=10, **{"loci-save": FM_A}),
    )

    assert "meta version 9 → 10" in section
    assert "reseeded automatically" in section
    assert "loci skills" not in section  # nothing for the user to run


def test_a_reworded_description_names_the_skill_and_the_command():
    """This is the one that needs an action: the stub in ~/.claude/skills/
    carries the frontmatter, so it is stale until `loci skills` is run."""
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": FM_A, "loci-query": FM_Q}),
        _snap(meta=9, **{"loci-save": FM_B, "loci-query": FM_Q}),
    )

    assert "`loci-save`" in section
    assert "loci-query" not in section
    assert "Run `loci skills`" in section


def test_a_new_skill_is_reported_as_new():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": FM_A}),
        _snap(meta=9, **{"loci-save": FM_A, "loci-inbox": FM_Q}),
    )

    assert "`loci-inbox` (new)" in section


def test_both_kinds_of_change_appear_together():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": FM_A}),
        _snap(meta=10, **{"loci-save": FM_B}),
    )

    assert "meta version 9 → 10" in section
    assert "`loci-save`" in section


def test_first_release_has_no_previous_versions():
    """Before the first tag there is nothing to diff against, and every skill
    reads as new rather than as a change."""
    section = release_notes.upgrade_section(
        release_notes.Snapshot(),
        _snap(meta=9, **{"loci-save": FM_A}),
    )

    assert "meta files are at version 9" in section
    assert "`loci-save` (new)" in section


def test_a_removed_skill_does_not_appear():
    """Nothing to install, so nothing to tell the user to run."""
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": FM_A, "loci-gone": FM_Q}),
        _snap(meta=9, **{"loci-save": FM_A}),
    )

    assert section == ""


def test_a_procedure_edit_alone_is_not_an_upgrade_step():
    """The stub is generated from the frontmatter and nothing else. The
    procedure below it is served live by the MCP server, so a change there
    reaches every install with nothing to run — reporting it would send the
    user to a command that prints "Everything is up to date"."""
    assert release_notes.parse_skill_frontmatter(FM_A + "step one\n") == FM_A
    assert release_notes.parse_skill_frontmatter(FM_A + "step two\n") == FM_A
    assert release_notes.parse_skill_frontmatter("no frontmatter\n") is None


# ---------------------------------------------------------------------------
# Opening the bump PR
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """A release run with the filesystem and every subprocess stubbed out.

    Returns the recorder: `.git` and `.gh` are the argument tuples each command
    was called with, in order, which is what most of these tests assert on —
    the ordering between them is the whole safety property of the one-step flow.
    """
    class Recorder:
        def __init__(self):
            self.git, self.gh, self.locked = [], [], False
            self.checks_pass = True
            self.pyproject = tmp_path / "pyproject.toml"
            self.pyproject.write_text(PYPROJECT)

        def run(self, args, **kwargs):
            command = tuple(args)
            if command[0] == "gh":
                self.gh.append(command[1:])
                failed = "checks" in command and not self.checks_pass
                return subprocess.CompletedProcess(
                    args, 1 if failed else 0, stdout="https://gh/pr/9\n", stderr="",
                )
            if command[:2] == ("uv", "lock"):
                self.locked = True
                # What `uv lock` really does: settle the lock on the new version.
                self.lock.write_text(f'name = "loci"\nversion = "{release.read_version(self.pyproject.read_text())}"\n')
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            raise AssertionError(f"unexpected subprocess: {command}")

    recorder = Recorder()
    recorder.lock = tmp_path / "uv.lock"
    recorder.lock.write_text('name = "loci"\nversion = "0.4.2"\n')

    monkeypatch.setattr(release, "PYPROJECT", recorder.pyproject)
    monkeypatch.setattr(release, "UV_LOCK", recorder.lock)
    monkeypatch.setattr(release, "require_clean_main", lambda: None)
    monkeypatch.setattr(release, "last_tag", lambda: "v0.4.1")
    monkeypatch.setattr(release, "changes_since", lambda tag: ["fix: a thing"])
    monkeypatch.setattr(release, "time", _NoSleep())
    monkeypatch.setattr(
        release, "git",
        lambda *args, **kwargs: (recorder.git.append(args), "")[1],
    )
    monkeypatch.setattr(release.subprocess, "run", recorder.run)
    return recorder


class _NoSleep:
    """time, with the waiting taken out — the retry loops are the point, not the delay."""
    def sleep(self, seconds): pass
    def monotonic(self): return 0.0


def test_a_failed_gh_pr_create_says_what_is_left_half_done(tmp_path, monkeypatch, capsys):
    """By the time `gh` runs, the bump is committed and pushed and we are on
    the release branch. Letting CalledProcessError escape gave a traceback, and
    the retry then failed with "on branch release/v0.4.3 — releases start from
    main", which describes none of that."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT)

    monkeypatch.setattr(release, "PYPROJECT", pyproject)
    monkeypatch.setattr(release, "UV_LOCK", tmp_path / "uv.lock")
    monkeypatch.setattr(release, "require_clean_main", lambda: None)
    monkeypatch.setattr(release, "git", lambda *args, **kwargs: "")
    monkeypatch.setattr(release, "uv_lock", lambda: None)
    monkeypatch.setattr(
        release.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1),
    )

    assert release.main(["bump", "patch", "--yes"]) == 1

    error = capsys.readouterr().err
    assert "release/v0.4.3" in error
    assert "gh pr create" in error


# ---------------------------------------------------------------------------
# The lockfile — the version lives in two files, not one
# ---------------------------------------------------------------------------

def test_the_repos_lockfile_agrees_with_pyproject():
    """The guard for the bug that made this necessary. uv.lock records a
    version for the local loci package too; when the bump PR moved only
    pyproject.toml, the next `uv run` rewrote the lock to settle the
    difference — and that `uv run` was the one inside `make release-publish`,
    which then found a dirty tree and refused to tag its own release."""
    declared = read_version((REPO_ROOT / "pyproject.toml").read_text())
    lock = (REPO_ROOT / "uv.lock").read_text()

    entry = re.search(
        r'^\[\[package\]\]\nname = "loci-vault"\nversion = "(\d+\.\d+\.\d+)"',
        lock,
        re.MULTILINE,
    )
    assert entry, "no [[package]] entry for loci-vault in uv.lock"
    assert entry.group(1) == declared, (
        f"uv.lock says loci-vault {entry.group(1)}, pyproject.toml says {declared}. "
        f"Run `uv lock`."
    )


def test_the_bump_locks_and_commits_both_files(fake_repo):
    """Bumping pyproject alone is what left the lock stale in the first place."""
    assert release.main(["bump", "patch", "--yes"]) == 0

    assert fake_repo.locked, "`uv lock` was never run"
    added = [args for args in fake_repo.git if args[0] == "add"]
    assert len(added) == 1
    assert str(fake_repo.pyproject) in added[0]
    assert str(fake_repo.lock) in added[0]


def test_a_failing_uv_lock_stops_the_release(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(
        release, "uv_lock",
        lambda: (_ for _ in ()).throw(release.ReleaseError("`uv lock` failed:\nboom")),
    )

    assert release.main(["release", "patch", "--yes"]) == 1
    assert "uv lock" in capsys.readouterr().err
    assert not [args for args in fake_repo.gh if args[:2] == ("pr", "merge")]


# ---------------------------------------------------------------------------
# The one-step flow
# ---------------------------------------------------------------------------

def test_one_step_waits_for_checks_before_it_merges(fake_repo):
    """main has no branch protection, so nothing server-side would refuse a
    merge on a red build. The ordering here is the only thing that does."""
    assert release.main(["release", "patch", "--yes"]) == 0

    kinds = [args[:2] for args in fake_repo.gh]
    assert ("pr", "create") in kinds
    assert ("pr", "checks") in kinds
    assert ("pr", "merge") in kinds
    assert kinds.index(("pr", "checks")) < kinds.index(("pr", "merge"))
    assert kinds.index(("pr", "create")) < kinds.index(("pr", "checks"))


def test_one_step_tags_only_after_the_merge(fake_repo):
    assert release.main(["release", "patch", "--yes"]) == 0

    tagged = [args for args in fake_repo.git if args[0] == "tag" and "-a" in args]
    assert tagged and "v0.4.3" in tagged[0]

    pushed = [args for args in fake_repo.git if args[:2] == ("push", "origin")]
    assert pushed[-1] == ("push", "origin", "v0.4.3")


def test_red_checks_leave_the_pr_unmerged_and_nothing_tagged(fake_repo, capsys):
    fake_repo.checks_pass = False

    assert release.main(["release", "patch", "--yes"]) == 1

    error = capsys.readouterr().err
    assert "nothing has been tagged" in error
    assert not [args for args in fake_repo.gh if args[:2] == ("pr", "merge")]
    assert not [args for args in fake_repo.git if args[0] == "tag" and "-a" in args]


def test_checks_are_not_believed_before_they_register(fake_repo, monkeypatch):
    """`gh pr checks` reports none for a few seconds after a push. Reading that
    as "all green" would merge before a single test had started."""
    answers = iter([False, False, True])
    monkeypatch.setattr(release, "checks_have_registered", lambda pr: next(answers))

    assert release.main(["release", "patch", "--yes"]) == 0
    assert next(answers, "exhausted") == "exhausted"


def test_a_squash_that_lands_the_wrong_version_is_not_tagged(fake_repo, monkeypatch, capsys):
    """The tag is cut from whatever main says after the merge, not from what
    was intended before it. If those differ, something else landed in between."""
    real_pull = release.git

    def git(*args, **kwargs):
        if args[:1] == ("pull",):
            fake_repo.pyproject.write_text(PYPROJECT.replace("0.4.2", "9.9.1"))
        return real_pull(*args, **kwargs)

    monkeypatch.setattr(release, "git", git)

    assert release.main(["release", "patch", "--yes"]) == 1
    assert "not 0.4.3" in capsys.readouterr().err


def test_declining_the_one_step_does_nothing(fake_repo, monkeypatch):
    monkeypatch.setattr(release, "confirm", lambda question, assume_yes: False)

    assert release.main(["release", "patch"]) == 1
    assert fake_repo.gh == []
    assert fake_repo.pyproject.read_text() == PYPROJECT


# ---------------------------------------------------------------------------
# Reading the versions back out of git
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True,
    )


@pytest.fixture
def history(tmp_path, monkeypatch):
    """A repo with one release tag and a bump after it.

    Built rather than mocked: the parsing is trivial, and the part that
    actually breaks is reading a file out of a ref that no longer matches the
    worktree.
    """
    repo = tmp_path / "repo"
    (repo / "src" / "loci" / "tools").mkdir(parents=True)
    (repo / "src" / "loci" / "skills" / "loci-save").mkdir(parents=True)

    vault_init = repo / "src" / "loci" / "tools" / "vault_init.py"
    skill = repo / "src" / "loci" / "skills" / "loci-save" / "SKILL.md"

    vault_init.write_text("META_VERSION = 9\n")
    skill.write_text(FM_A + "procedure\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "first")
    _git(repo, "tag", "v0.1.0")

    vault_init.write_text("META_VERSION = 10\n")
    skill.write_text(FM_B + "procedure\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "second")

    # Point the module at this repo rather than chdir-ing: release_notes pins
    # every git call to REPO_ROOT, so the tests have to move the same knob.
    monkeypatch.setattr(release_notes, "REPO_ROOT", repo)
    return repo


def test_snapshot_reads_an_old_tag_not_the_worktree(history):
    old = release_notes.snapshot("v0.1.0")

    assert old.meta_version == 9
    assert old.skills == {"loci-save": FM_A}


def test_snapshot_reads_the_current_ref(history):
    current = release_notes.snapshot("HEAD")

    assert current.meta_version == 10
    assert current.skills == {"loci-save": FM_B}


def test_snapshot_of_history_composes_the_real_section(history):
    section = release_notes.upgrade_section(
        release_notes.snapshot("v0.1.0"), release_notes.snapshot("HEAD")
    )

    assert "meta version 9 → 10" in section
    assert "`loci-save`" in section
    assert "Run `loci skills`" in section


def test_empty_previous_ref_is_the_first_release(history):
    """What the workflow passes before any tag exists."""
    assert release_notes.snapshot("") == release_notes.Snapshot()


def test_an_unresolvable_ref_is_an_error_not_an_empty_snapshot(history):
    """Swallowing it published notes with no "Upgrading" section — no reseed
    warning, no `loci skills` instruction, and nothing in the log to say so."""
    with pytest.raises(release_notes.GitError):
        release_notes.snapshot("v9.9.9")


def test_main_fails_rather_than_printing_empty_notes(history, capsys):
    assert release_notes.main(["v9.9.9", "HEAD"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "v9.9.9" in captured.err


def test_git_is_run_against_the_repo_not_the_callers_cwd(history, tmp_path, monkeypatch):
    """`make release` and the workflow both happen to run from the root. From
    anywhere else the old code returned nothing at all, silently."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert release_notes.snapshot("HEAD").skills == {"loci-save": FM_B}


# ---------------------------------------------------------------------------
# The wheel has to carry the UI
#
# `uv build` produces a backend-only wheel: app/ is not packaged, and an
# installed Loci has no Node to build it with. Two pieces of configuration keep
# the frontend in the artifact, and both are the kind of thing a later
# simplification quietly removes.
# ---------------------------------------------------------------------------

RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
MAKEFILE = REPO_ROOT / "Makefile"


def test_the_release_builds_the_wheel_through_make():
    """`make wheel` compiles the frontend in first. A bare `uv build` here is
    the regression: it succeeds, publishes, and ships no UI."""
    workflow = RELEASE_WORKFLOW.read_text()

    assert "run: make wheel" in workflow
    assert "run: uv build" not in workflow


def test_the_release_has_node_available():
    """No Node on the runner means `make wheel` cannot build the bundle."""
    assert "actions/setup-node" in RELEASE_WORKFLOW.read_text()


def test_make_wheel_puts_the_bundle_where_hatch_looks():
    """The Makefile's copy target and pyproject's artifacts entry have to name
    the same directory, or the build silently drops the UI."""
    makefile = MAKEFILE.read_text()

    assert "npm run build" in makefile
    assert "src/loci/static" in makefile


def test_the_bundle_is_declared_as_a_build_artifact():
    """src/loci/static/ is gitignored, and hatchling honours .gitignore. Without
    this entry the directory is built, copied, and then left out of the wheel
    with no error."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()

    assert 'artifacts = ["src/loci/static/**"]' in pyproject
    assert "[tool.hatch.build]" in pyproject


def test_the_wheel_build_cannot_bake_in_the_builders_token():
    """vite.config.js inlines config.yml's api_token into the bundle so `make
    dev` needs no setup. Left alone here, the builder's live token ships inside
    the wheel to whoever installs it. LOCI_API_TOKEN="" does not help —
    readApiToken() tests truthiness and falls through to the file."""
    makefile = MAKEFILE.read_text()
    wheel_recipe = makefile.split("\nwheel:", 1)[1].split("\n\n", 1)[0]

    assert "LOCI_CONFIG=/nonexistent npm run build" in wheel_recipe


def test_the_wheel_build_fails_when_the_bundle_is_missing():
    """The check that the UI made it in has to be able to fail. Piping grep -c
    into xargs hid a zero count behind xargs' exit status, so a wheel that
    dropped the bundle printed "0 frontend files packaged" and succeeded."""
    makefile = MAKEFILE.read_text()
    wheel_recipe = makefile.split("\nwheel:", 1)[1].split("\n\n", 1)[0]

    assert "exit 1" in wheel_recipe, "the packaging check has no failing branch"
    assert "| xargs" not in wheel_recipe


def test_the_bundle_is_not_committed():
    """It is build output. Committing it would put a minified diff in every
    release PR and let a stale bundle ship from a checkout."""
    gitignore = (REPO_ROOT / ".gitignore").read_text()

    assert "/src/loci/static/" in gitignore

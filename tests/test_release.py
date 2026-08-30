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

def _snap(meta=None, **skills):
    return release_notes.Snapshot(meta_version=meta, skills=skills)


def test_nothing_moved_produces_no_section():
    """Most releases touch neither. An empty string is what keeps a pointless
    'Upgrading: nothing to do' heading off every set of notes."""
    before = _snap(meta=9, **{"loci-save": 23})
    assert release_notes.upgrade_section(before, before) == ""


def test_meta_bump_says_it_reseeds_itself():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": 23}),
        _snap(meta=10, **{"loci-save": 23}),
    )

    assert "meta version 9 → 10" in section
    assert "reseeded automatically" in section
    assert "loci skills" not in section  # nothing for the user to run


def test_skill_bump_names_the_skill_and_the_command():
    """This is the one that needs an action: the installed copy in
    ~/.claude/skills/ is stale until `loci skills` is run."""
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": 23, "loci-query": 1}),
        _snap(meta=9, **{"loci-save": 24, "loci-query": 1}),
    )

    assert "`loci-save` (v23 → v24)" in section
    assert "loci-query" not in section
    assert "Run `loci skills`" in section


def test_a_new_skill_is_reported_as_new():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": 23}),
        _snap(meta=9, **{"loci-save": 23, "loci-inbox": 4}),
    )

    assert "`loci-inbox` (new, v4)" in section


def test_both_kinds_of_change_appear_together():
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": 23}),
        _snap(meta=10, **{"loci-save": 24}),
    )

    assert "meta version 9 → 10" in section
    assert "v23 → v24" in section


def test_first_release_has_no_previous_versions():
    """Before the first tag there is nothing to diff against, and every version
    reads as new rather than as a change."""
    section = release_notes.upgrade_section(
        release_notes.Snapshot(),
        _snap(meta=9, **{"loci-save": 23}),
    )

    assert "meta files are at version 9" in section
    assert "`loci-save` (new, v23)" in section


def test_a_removed_skill_does_not_appear():
    """Nothing to install, so nothing to tell the user to run."""
    section = release_notes.upgrade_section(
        _snap(meta=9, **{"loci-save": 23, "loci-gone": 2}),
        _snap(meta=9, **{"loci-save": 23}),
    )

    assert section == ""


# ---------------------------------------------------------------------------
# Phase 1 — opening the bump PR
# ---------------------------------------------------------------------------

def test_a_failed_gh_pr_create_says_what_is_left_half_done(tmp_path, monkeypatch, capsys):
    """By the time `gh` runs, the bump is committed and pushed and we are on
    the release branch. Letting CalledProcessError escape gave a traceback, and
    the retry then failed with "on branch release/v0.4.3 — releases start from
    main", which describes none of that."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT)

    monkeypatch.setattr(release, "PYPROJECT", pyproject)
    monkeypatch.setattr(release, "require_clean_main", lambda: None)
    monkeypatch.setattr(release, "git", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        release.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1),
    )

    assert release.main(["bump", "patch", "--yes"]) == 1

    error = capsys.readouterr().err
    assert "release/v0.4.3" in error
    assert "gh pr create" in error


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
    skill.write_text("---\nskill_version: 23\n---\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "first")
    _git(repo, "tag", "v0.1.0")

    vault_init.write_text("META_VERSION = 10\n")
    skill.write_text("---\nskill_version: 24\n---\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "second")

    # Point the module at this repo rather than chdir-ing: release_notes pins
    # every git call to REPO_ROOT, so the tests have to move the same knob.
    monkeypatch.setattr(release_notes, "REPO_ROOT", repo)
    return repo


def test_snapshot_reads_an_old_tag_not_the_worktree(history):
    old = release_notes.snapshot("v0.1.0")

    assert old.meta_version == 9
    assert old.skills == {"loci-save": 23}


def test_snapshot_reads_the_current_ref(history):
    current = release_notes.snapshot("HEAD")

    assert current.meta_version == 10
    assert current.skills == {"loci-save": 24}


def test_snapshot_of_history_composes_the_real_section(history):
    section = release_notes.upgrade_section(
        release_notes.snapshot("v0.1.0"), release_notes.snapshot("HEAD")
    )

    assert "meta version 9 → 10" in section
    assert "`loci-save` (v23 → v24)" in section


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

    assert release_notes.snapshot("HEAD").skills == {"loci-save": 24}


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

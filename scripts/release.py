"""
scripts/release.py
Drives a release. One command, or the same thing in two halves.

    make release BUMP=minor     # bump, PR, wait for CI, merge, tag, push


    make release-bump BUMP=minor    # or the halves: open the PR
    <merge the PR>
    make release-publish            # tag the merged commit

main is never written to by hand either way — the version change lands as a
PR like anything else. What the one-step flow automates is the waiting and
the merge, which is all the two phases ever asked a human to do. Use the
halves when CI wants watching by hand, or when a one-step run died partway.

The bump changes two lines: the version in pyproject.toml, and the version
uv.lock records for the local package. Both, because `uv run` re-resolves the
lock the moment those two disagree — and the first thing to run `uv run`
afterwards was `make release-publish` itself, which dirtied the tree its own
clean-tree guard then refused to act on.

Tagging is what .github/workflows/release.yml fires on: it rebuilds, verifies
the tag against pyproject.toml, and publishes the wheel to a GitHub Release.

The version is yours to pick — patch, minor or major — and nothing here
guesses it from commit messages. What is automated is the part that went wrong
without it: `version = "0.1.0"` sat unchanged for 141 commits, so every install
reported the same version. The workflow's tag check is what makes that
impossible now.

This script is not packaged. It reaches for repo paths freely, which nothing
under src/loci/ may do.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
MAIN_BRANCH = "main"
PARTS = ("major", "minor", "patch")

# How long to wait for a PR's checks before giving up. The e2e suite is the
# long pole; 30 minutes is several times its worst run, and the timeout exists
# so a wedged check cannot hang the terminal forever rather than to be tight.
CHECKS_TIMEOUT = 30 * 60

# Anchored to the start of a line so a version pinned inside a dependency
# string cannot match. The [project] table's own version is the first such
# line in the file.
_VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


class ReleaseError(Exception):
    """A guard failed. The message is what the user sees; no traceback."""


# ---------------------------------------------------------------------------
# Version arithmetic — pure, so the tests can exercise it directly
# ---------------------------------------------------------------------------

def read_version(pyproject_text: str) -> str:
    match = _VERSION_RE.search(pyproject_text)
    if not match:
        raise ReleaseError("no `version = \"x.y.z\"` line found in pyproject.toml")
    return ".".join(match.groups())


def bump_version(version: str, part: str) -> str:
    if part not in PARTS:
        raise ReleaseError(f"unknown bump {part!r} — expected one of {', '.join(PARTS)}")
    major, minor, patch = (int(n) for n in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def set_version(pyproject_text: str, new_version: str) -> str:
    """Replace the version line, and only the first one."""
    if not _VERSION_RE.search(pyproject_text):
        raise ReleaseError("no `version = \"x.y.z\"` line found in pyproject.toml")
    return _VERSION_RE.sub(f'version = "{new_version}"', pyproject_text, count=1)


def tag_name(version: str) -> str:
    return f"v{version}"


def version_from_tag(tag: str) -> str:
    """`v0.2.0` -> `0.2.0`. Anything else is not a release tag."""
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ReleaseError(f"{tag!r} is not a release tag — expected vMAJOR.MINOR.PATCH")
    return tag[1:]


def check_tag(tag: str, pyproject_text: str) -> str:
    """The workflow's gate: the tag and pyproject.toml must agree.

    This is the whole reason the version can be hand-picked and still be
    trusted. A tag pushed without the bump PR having merged fails here, before
    a wheel claiming the wrong version reaches anybody.
    """
    tagged = version_from_tag(tag)
    declared = read_version(pyproject_text)
    if tagged != declared:
        raise ReleaseError(
            f"tag {tag} does not match pyproject.toml version {declared}.\n"
            f"The version-bump PR for {tagged} has probably not merged yet."
        )
    return tagged


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def require_clean_main() -> None:
    """Both phases start from an up-to-date main with nothing uncommitted."""
    branch = current_branch()
    if branch != MAIN_BRANCH:
        raise ReleaseError(f"on branch {branch} — releases start from {MAIN_BRANCH}")

    if git("status", "--porcelain"):
        raise ReleaseError("working tree is dirty — commit or stash first")

    git("fetch", "origin", MAIN_BRANCH)
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", f"origin/{MAIN_BRANCH}")
    if local != remote:
        raise ReleaseError(
            f"{MAIN_BRANCH} is not in sync with origin — pull (or push) first"
        )


def last_tag() -> str:
    """The most recent release tag, or "" before the first release."""
    return git("describe", "--tags", "--abbrev=0", "--match", "v*", check=False)


def changes_since(tag: str) -> list[str]:
    """Subjects of the commits since a tag — the merged PRs, in practice."""
    span = f"{tag}..HEAD" if tag else "HEAD"
    log = git("log", span, "--no-merges", "--pretty=%s", check=False)
    return [line for line in log.splitlines() if line]


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise ReleaseError("not a terminal — re-run with --yes")
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def uv_lock() -> None:
    """Re-resolve uv.lock against the version just written to pyproject.toml.

    uv.lock records a version for the local `loci` package too, so bumping
    pyproject.toml alone leaves the two disagreeing — and `uv run` rewrites
    the lock to settle it at the start of the very next command. That command
    was `make release-publish`, which then found the tree dirty and refused to
    tag. Locking here keeps the disagreement from ever existing.
    """
    result = subprocess.run(
        ["uv", "lock"], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ReleaseError(f"`uv lock` failed:\n{result.stderr.strip()}")


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise ReleaseError(
            f"`gh {' '.join(args)}` failed"
            + (f":\n{detail}" if detail else " — is gh installed and authenticated?")
        )
    return result.stdout.strip()


def checks_have_registered(pr: str) -> bool:
    """Whether GitHub has the workflow runs for this push yet.

    For the first few seconds after a push `gh pr checks` reports none at all.
    Taking that for a verdict would merge the PR before a single test had
    started, which is the one thing this whole gate exists to prevent.
    """
    probe = subprocess.run(
        ["gh", "pr", "checks", pr], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return "no checks reported" not in f"{probe.stdout}{probe.stderr}".lower()


def wait_for_checks(pr: str) -> None:
    """Block until the PR's checks finish, and fail if any of them did.

    `gh pr checks --watch` polls until every check has a conclusion and exits
    non-zero if one failed — the same look at the PR a human takes before
    merging it. Its output is left to stream, because the whole point of a
    command that blocks for several minutes is being able to see why.
    """
    deadline = time.monotonic() + CHECKS_TIMEOUT
    while not checks_have_registered(pr):
        if time.monotonic() >= deadline:
            raise ReleaseError(f"no checks ever reported on PR {pr} — nothing tagged.")
        time.sleep(10)

    result = subprocess.run(
        ["gh", "pr", "checks", pr, "--watch", "--interval", "15"],
        cwd=REPO_ROOT,
        timeout=max(1, int(deadline - time.monotonic())),
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"checks did not pass on PR {pr} — nothing has been tagged.\n"
            f"Fix them, then finish with `make release-publish` once it merges."
        )


# ---------------------------------------------------------------------------
# Opening the bump PR — the first half of either flow
# ---------------------------------------------------------------------------

def plan_bump(part: str) -> tuple[str, str, str]:
    """Work out what this release would be. Returns (current, new, tag)."""
    current = read_version(PYPROJECT.read_text())
    new = bump_version(current, part)
    tag = tag_name(new)

    if git("tag", "--list", tag):
        raise ReleaseError(f"{tag} already exists — pick a different bump")
    return current, new, tag


def announce(current: str, new: str, part: str) -> None:
    previous = last_tag()
    changes = changes_since(previous)
    print(f"\nSince {previous or 'the start of the repo'} — {len(changes)} commits:\n")
    for subject in changes:
        print(f"  {subject}")
    print(f"\n{current} → {new}  ({part})")


def open_bump_pr(new: str, tag: str) -> tuple[str, str]:
    """Branch, bump both files, push, open the PR. Returns (branch, pr url)."""
    branch = f"release/{tag}"
    git("switch", "-c", branch)

    PYPROJECT.write_text(set_version(PYPROJECT.read_text(), new))
    uv_lock()
    git("add", str(PYPROJECT), str(UV_LOCK))
    git("commit", "-m", f"chore: release {tag}")
    git("push", "-u", "origin", branch)

    body = (
        f"Version bump for {tag}, in pyproject.toml and the version uv.lock "
        f"records for the local package.\n\n"
        f"Merging this and tagging is what publishes the release: the workflow "
        f"builds the wheel and composes the notes."
    )
    result = subprocess.run(
        ["gh", "pr", "create", "--title", f"chore: release {tag}", "--body", body],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # By now the bump is committed and pushed and we are standing on the
        # release branch. A traceback here left the next `make release` failing
        # on "on branch release/vX.Y.Z — releases start from main", which says
        # nothing about what actually went wrong.
        raise ReleaseError(
            f"`gh pr create` failed (is gh installed and authenticated?).\n"
            f"{branch} is pushed with the bump to {new}; open its PR by hand, "
            f"or delete the branch and start over."
        )

    url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    print(url or f"opened the PR for {branch}")
    return branch, url


def cmd_bump(args: argparse.Namespace) -> int:
    """Half one on its own: leave the PR open for a human to merge."""
    require_clean_main()
    current, new, tag = plan_bump(args.part)
    announce(current, new, args.part)

    if not confirm(f"Open the release PR for {tag}?", args.yes):
        print("Nothing done.")
        return 1

    open_bump_pr(new, tag)
    print(f"\nNext: merge the PR, then `git checkout main && git pull && make release-publish`.")
    return 0


# ---------------------------------------------------------------------------
# The whole thing in one command
# ---------------------------------------------------------------------------

def cmd_release(args: argparse.Namespace) -> int:
    """Bump, PR, wait for CI, merge, tag — with one confirmation up front.

    The merge is the step this adds, and it is deliberately gated on
    wait_for_checks rather than on the repo refusing a red merge: main here
    has no branch protection, so nothing server-side would stop a tag from
    being cut on a failing build. That gate is this function.
    """
    require_clean_main()
    current, new, tag = plan_bump(args.part)
    announce(current, new, args.part)

    print(
        f"\nThis opens the PR for {tag}, waits for its checks, merges it, "
        f"and pushes the tag.\nThe wait is however long the e2e suite takes."
    )
    if not confirm(f"Release {tag}?", args.yes):
        print("Nothing done.")
        return 1

    branch, url = open_bump_pr(new, tag)
    pr = url or branch

    print(f"\nWaiting for checks on {pr} …")
    wait_for_checks(pr)

    print(f"\nChecks passed. Merging {pr}.")
    gh("pr", "merge", pr, "--squash", "--delete-branch")

    # gh leaves us on main with the release branch gone, but it fetches rather
    # than pulls — main still has to be moved onto the merge before it is tagged.
    git("switch", MAIN_BRANCH, check=False)
    git("pull", "origin", MAIN_BRANCH)
    git("branch", "-D", branch, check=False)

    # The merge is a squash, so main's version is only as good as what landed.
    # Reading it back is the same check the workflow runs against the tag.
    merged = read_version(PYPROJECT.read_text())
    if merged != new:
        raise ReleaseError(
            f"{MAIN_BRANCH} says version {merged} after the merge, not {new}. "
            f"Nothing tagged."
        )

    return tag_and_push(new, assume_yes=True)


# ---------------------------------------------------------------------------
# Phase 2 — tag the merged bump
# ---------------------------------------------------------------------------

def cmd_publish(args: argparse.Namespace) -> int:
    require_clean_main()
    return tag_and_push(read_version(PYPROJECT.read_text()), assume_yes=args.yes)


def tag_and_push(version: str, assume_yes: bool) -> int:
    tag = tag_name(version)

    if git("tag", "--list", tag):
        raise ReleaseError(f"{tag} already exists locally — nothing to publish")
    if git("ls-remote", "--tags", "origin", tag, check=False):
        raise ReleaseError(f"{tag} already exists on origin — nothing to publish")
    if tag == last_tag():
        raise ReleaseError(f"{tag} is already the latest tag — bump the version first")

    print(f"\nTagging {git('rev-parse', '--short', 'HEAD')} on {MAIN_BRANCH} as {tag}.")
    if not confirm(f"Push {tag}?", assume_yes):
        print("Nothing done.")
        return 1

    git("tag", "-a", tag, "-m", f"Loci {tag}")
    git("push", "origin", tag)
    print(f"\nPushed {tag}. The release workflow builds the wheel and publishes the notes.")
    return 0


# ---------------------------------------------------------------------------
# Used by the workflow, not by a human
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    print(check_tag(args.tag, PYPROJECT.read_text()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release.py", description=__doc__.split("\n")[2])
    sub = parser.add_subparsers(dest="command", required=True)

    release = sub.add_parser("release", help="Bump, PR, wait, merge, tag — in one.")
    release.add_argument("part", choices=PARTS)
    release.add_argument("-y", "--yes", action="store_true")
    release.set_defaults(func=cmd_release)

    bump = sub.add_parser("bump", help="Open the version-bump PR and stop.")
    bump.add_argument("part", choices=PARTS)
    bump.add_argument("-y", "--yes", action="store_true")
    bump.set_defaults(func=cmd_bump)

    publish = sub.add_parser("publish", help="Tag merged main and push the tag.")
    publish.add_argument("-y", "--yes", action="store_true")
    publish.set_defaults(func=cmd_publish)

    check = sub.add_parser("check", help="Verify a tag matches pyproject.toml.")
    check.add_argument("tag")
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

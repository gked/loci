"""
scripts/release.py
Drives a release. Two phases, because main is never written to by hand.

    make release BUMP=minor     # phase 1 — open the version-bump PR
    <merge the PR>
    make release-publish        # phase 2 — tag the merged commit

Phase 1 decides the number and opens a PR that changes exactly one line in
pyproject.toml. Phase 2 tags the merged result and pushes the tag, which is
what .github/workflows/release.yml fires on: it rebuilds, verifies the tag
against pyproject.toml, and publishes the wheel to a GitHub Release.

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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAIN_BRANCH = "main"
PARTS = ("major", "minor", "patch")

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


# ---------------------------------------------------------------------------
# Phase 1 — open the bump PR
# ---------------------------------------------------------------------------

def cmd_bump(args: argparse.Namespace) -> int:
    require_clean_main()

    text = PYPROJECT.read_text()
    current = read_version(text)
    new = bump_version(current, args.part)
    tag = tag_name(new)

    if git("tag", "--list", tag):
        raise ReleaseError(f"{tag} already exists — pick a different bump")

    previous = last_tag()
    changes = changes_since(previous)
    print(f"\nSince {previous or 'the start of the repo'} — {len(changes)} commits:\n")
    for subject in changes:
        print(f"  {subject}")

    print(f"\n{current} → {new}  ({args.part})")
    if not confirm(f"Open the release PR for {tag}?", args.yes):
        print("Nothing done.")
        return 1

    branch = f"release/{tag}"
    git("switch", "-c", branch)
    PYPROJECT.write_text(set_version(text, new))
    git("add", str(PYPROJECT))
    git("commit", "-m", f"chore: release {tag}")
    git("push", "-u", "origin", branch)

    body = (
        f"Version bump for {tag}.\n\n"
        f"Merge this, then run `make release-publish` on main to tag it. "
        f"The release workflow builds the wheel and publishes the notes."
    )
    result = subprocess.run(
        ["gh", "pr", "create", "--title", f"chore: release {tag}", "--body", body],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        # The bump is already committed and pushed, and we are standing on the
        # release branch. A traceback here left the next `make release` failing
        # on "on branch release/vX.Y.Z — releases start from main", which says
        # nothing about what actually went wrong.
        raise ReleaseError(
            f"`gh pr create` failed (is gh installed and authenticated?).\n"
            f"{branch} is pushed with the bump to {new}; open its PR by hand, "
            f"or delete the branch and start over."
        )
    print(f"\nNext: merge the PR, then `git checkout main && git pull && make release-publish`.")
    return 0


# ---------------------------------------------------------------------------
# Phase 2 — tag the merged bump
# ---------------------------------------------------------------------------

def cmd_publish(args: argparse.Namespace) -> int:
    require_clean_main()

    version = read_version(PYPROJECT.read_text())
    tag = tag_name(version)

    if git("tag", "--list", tag):
        raise ReleaseError(f"{tag} already exists locally — nothing to publish")
    if git("ls-remote", "--tags", "origin", tag, check=False):
        raise ReleaseError(f"{tag} already exists on origin — nothing to publish")
    if tag == last_tag():
        raise ReleaseError(f"{tag} is already the latest tag — bump the version first")

    print(f"\nTagging {git('rev-parse', '--short', 'HEAD')} on {MAIN_BRANCH} as {tag}.")
    if not confirm(f"Push {tag}?", args.yes):
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

    bump = sub.add_parser("bump", help="Open the version-bump PR.")
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

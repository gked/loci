"""
scripts/release_notes.py
Compose the "Upgrading" section that opens a release's notes.

GitHub already assembles the list of merged PRs, and that is the body of the
notes. What it cannot know is which of those PRs changed something the user has
to act on after upgrading. Two things qualify:

  * META_VERSION moved — the seeded files under vault/meta/ are reseeded on the
    next start, without the user doing anything. Worth stating, because their
    vault changes underneath them.
  * a skill stub changed — a skill was added, or its frontmatter (the trigger
    description Claude Code matches on) was reworded. The stub in
    ~/.claude/skills/ carries that frontmatter and nothing else, so it is now
    stale until `loci skills` is run. That one needs an action, so it must
    not be buried in a PR list. A change to the procedure itself is not
    reported: the MCP server serves it live, and nothing is installed.

Nothing here reaches a repo at import time: the two version snapshots are read
out of git by the caller and passed in as text, so the interesting half is
pure and testable.

Usage (from the release workflow):
    python scripts/release_notes.py <previous-ref> <current-ref>
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Every git call is pinned here rather than left to the caller's cwd. The
# workflow happens to run from the repo root, but a lookup that quietly
# returned nothing from anywhere else was exactly how this file could publish
# notes with no "Upgrading" section — the one thing it exists to write.
REPO_ROOT = Path(__file__).resolve().parent.parent

VAULT_INIT = "src/loci/tools/vault_init.py"
SKILLS_GLOB = "src/loci/skills"

_META_RE = re.compile(r"^META_VERSION\s*=\s*(\d+)\s*$", re.MULTILINE)


@dataclass
class Snapshot:
    """The user-facing version numbers at one point in history."""

    meta_version: int | None = None
    # Skill name -> its SKILL.md frontmatter. That block is what the installed
    # stub is generated from, so it changing is what makes the stub stale.
    skills: dict[str, str] = field(default_factory=dict)


def parse_meta_version(text: str) -> int | None:
    match = _META_RE.search(text)
    return int(match.group(1)) if match else None


def parse_skill_frontmatter(text: str) -> str | None:
    """The frontmatter block of a SKILL.md, or None if it has none.

    Kept in step with loci.skill_assembly.split_frontmatter rather than
    importing it: this script runs in the release workflow before the package
    is installed.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    return None if end == -1 else text[: end + len("\n---\n")]


def meta_line(previous: Snapshot, current: Snapshot) -> str | None:
    """The reseed note, or None when the meta files did not move."""
    before, after = previous.meta_version, current.meta_version
    if after is None or before == after:
        return None
    if before is None:
        return (
            f"- Vault meta files are at version {after}. They are seeded into "
            "`vault/meta/` the next time Loci starts."
        )
    return (
        f"- Vault meta files changed (meta version {before} → {after}). They are "
        "reseeded automatically the next time Loci starts; your own "
        "`*-user.*` files are left alone."
    )


def skill_lines(previous: Snapshot, current: Snapshot) -> list[str]:
    """One line naming every skill whose stub changed, plus the action to take."""
    changed = []
    for name in sorted(current.skills):
        after = current.skills[name]
        before = previous.skills.get(name)
        if before is None:
            changed.append(f"`{name}` (new)")
        elif before != after:
            changed.append(f"`{name}`")

    if not changed:
        return []
    return [
        f"- Skills changed: {', '.join(changed)}. Run `loci skills` to update "
        "the stubs in `~/.claude/skills/`, then restart Claude Code.",
    ]


def upgrade_section(previous: Snapshot, current: Snapshot) -> str:
    """The whole section, or "" when nothing needs saying.

    Empty is the common case — most releases touch neither — and an empty
    string is what keeps a boilerplate "Upgrading: nothing to do" heading out
    of every set of notes.
    """
    lines = [line for line in (meta_line(previous, current),) if line]
    lines += skill_lines(previous, current)
    if not lines:
        return ""
    return "## Upgrading\n\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reading the snapshots out of git
# ---------------------------------------------------------------------------

class GitError(RuntimeError):
    """A git command these notes depend on failed."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    )


def _require_ref(ref: str) -> None:
    """Fail loudly on a ref git cannot resolve.

    Without this, a bad ref makes every lookup below return nothing and the
    release publishes notes that silently omit the upgrade steps. Checking once
    is also what lets _show() treat its own failure as "the file was not in
    that commit" rather than as an error it has to guess about.
    """
    if _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise GitError(f"{ref!r} is not a commit in {REPO_ROOT}")


def _show(ref: str, path: str) -> str | None:
    """`git show <ref>:<path>`, or None when the file did not exist there."""
    result = _git("show", f"{ref}:{path}")
    return result.stdout if result.returncode == 0 else None


def _skill_paths(ref: str) -> list[str]:
    """The SKILL.md paths present at a ref. Read from git, not the worktree —
    a skill added or removed since then must not be read off disk."""
    result = _git("ls-tree", "-r", "--name-only", ref, SKILLS_GLOB)
    if result.returncode != 0:
        raise GitError(f"git ls-tree {ref} failed:\n{result.stderr.strip()}")
    return [p for p in result.stdout.splitlines() if p.endswith("/SKILL.md")]


def snapshot(ref: str) -> Snapshot:
    """Read a ref's meta version and skill frontmatter out of git."""
    if not ref:
        return Snapshot()

    _require_ref(ref)
    vault_init = _show(ref, VAULT_INIT)
    snap = Snapshot(meta_version=parse_meta_version(vault_init) if vault_init else None)

    for path in _skill_paths(ref):
        text = _show(ref, path)
        frontmatter = parse_skill_frontmatter(text) if text else None
        if frontmatter is not None:
            # ".../skills/loci-save/SKILL.md" -> "loci-save"
            snap.skills[path.split("/")[-2]] = frontmatter
    return snap


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: release_notes.py <previous-ref> <current-ref>", file=sys.stderr)
        return 2

    previous_ref, current_ref = args
    try:
        section = upgrade_section(snapshot(previous_ref), snapshot(current_ref))
    except GitError as error:
        # Better to fail the release than to publish notes that quietly leave
        # out "run `loci skills`".
        print(f"release_notes: {error}", file=sys.stderr)
        return 1
    print(section, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Install the packaged Loci skills into a Claude Code skills directory.

This is how an installed Loci — a wheel, with no checkout anywhere on the
machine — gets its skills in front of Claude Code. The skills ship inside the
package (`loci/skills/<name>/`), and this module copies them to
`~/.claude/skills/<name>/`, which is where Claude Code looks.

Copies, not symlinks, by default. A symlink into the package works beautifully
from a checkout and not at all from an install: `uv tool install --upgrade`
replaces the site-packages tree wholesale, so every link into it dangles. The
`link=True` path exists for callers that *know* they are running from a
checkout — setup.py does, because live-editing a skill is the point there — and
is never inferred here. Inferring it would mean asking "am I inside a repo?" at
runtime, which an installed copy cannot answer and must not try to.

What is no longer packaged is also taken out. A skill renamed or dropped
upstream would otherwise sit in ~/.claude/skills/ forever with Claude Code
still loading it — beside its replacement, in the rename case. Only entries
this installer could have created are ever removed; see _orphans().

The copies are also what makes `skill_version` mean anything. Each SKILL.md
opens by comparing its own version against the packaged one via `read_skill`;
under a symlink those are the same bytes and the check can never fire. Under a
copy it becomes a real "your skill is stale, run `loci skills`" signal.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# The skills live beside this module, inside the package. Not a repo path:
# this resolves to site-packages on an installed copy, which is the point.
SKILLS_SOURCE = Path(__file__).parent / "skills"

# references/ sits under skills/ but is not a skill — it holds the canonical
# ontology and relation YAML the registries read and vault_init seeds. Copying
# it into ~/.claude/skills/ would present it to Claude Code as a broken skill.
NOT_SKILLS = frozenset({"references"})

DEFAULT_SKILLS_ROOT = Path.home() / ".claude" / "skills"

# Every skill Loci ships is named this way, and it is the only marker a copied
# skill directory carries once it is out of the package. See _orphans().
SKILL_NAME_PREFIX = "loci-"

_VERSION_RE = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)

# What to do with each skill. Only INSTALL and UPDATE write anything.
INSTALL = "install"
UPDATE = "update"
CURRENT = "up to date"
LINKED = "dev symlink"
AHEAD = "newer than packaged"
REMOVE = "removed — no longer shipped"


@dataclass(frozen=True)
class SkillStatus:
    """One skill's packaged version, installed version, and what to do.

    `source` is None for a REMOVE: the skill is only in the destination, which
    is the whole reason it is being taken out.
    """

    name: str
    source: Path | None
    dest: Path
    packaged_version: int | None
    installed_version: int | None
    action: str

    @property
    def writes(self) -> bool:
        return self.action in (INSTALL, UPDATE, REMOVE)


def read_skill_version(skill_md: Path) -> int | None:
    """The `skill_version` in a SKILL.md's frontmatter, or None if unreadable.

    None is a legitimate answer, not an error: a hand-edited or truncated
    SKILL.md still sits in the skills directory and still has to be reported.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def packaged_skills(source: Path | None = None) -> list[Path]:
    """Every shipped skill directory, in a stable order.

    The default resolves at call time rather than in the signature: a default
    bound at import time cannot be monkeypatched, and the tests need to point
    this at a fixture tree.
    """
    source = SKILLS_SOURCE if source is None else source
    if not source.is_dir():
        return []
    return sorted(
        d for d in source.iterdir()
        if d.is_dir() and d.name not in NOT_SKILLS and (d / "SKILL.md").is_file()
    )


def _source_root(source: Path | None) -> Path:
    """The skills directory packaged_skills() reads, resolved the same way."""
    return SKILLS_SOURCE if source is None else source


def _points_into_source(dest: Path, source_root: Path) -> bool:
    """True when dest is a symlink aimed anywhere inside the packaged tree.

    Deliberately weaker than _links_into_package(): the target here no longer
    exists — it is a skill that was renamed or dropped — so the comparison is
    against the tree rather than a specific skill. resolve() answers for a
    dangling link too, which is exactly the case this has to catch.
    """
    if not dest.is_symlink():
        return False
    try:
        return dest.resolve().is_relative_to(source_root.resolve())
    except OSError:
        return False


def _orphans(skills_root: Path, packaged: set[str], source_root: Path) -> list[SkillStatus]:
    """Installed skills Loci put there and no longer ships.

    A skill renamed or deleted upstream otherwise sits in ~/.claude/skills/
    forever, and Claude Code keeps loading it — for a rename, alongside the new
    one. Only two things qualify, both unambiguously ours: a symlink into this
    package's skills tree, whatever it is called, and a directory whose name
    carries the packaged prefix. Anything else in there belongs to the user.
    """
    if not skills_root.is_dir():
        return []

    stale = []
    for dest in sorted(skills_root.iterdir()):
        if dest.name in packaged:
            continue
        ours = _points_into_source(dest, source_root) or (
            dest.name.startswith(SKILL_NAME_PREFIX) and (dest / "SKILL.md").is_file()
        )
        if not ours:
            continue
        stale.append(
            SkillStatus(
                name=dest.name,
                source=None,
                dest=dest,
                packaged_version=None,
                installed_version=read_skill_version(dest / "SKILL.md"),
                action=REMOVE,
            )
        )
    return stale


def _links_into_package(dest: Path, source: Path) -> bool:
    """True when dest is a symlink already pointing at this package's skill.

    That is the checkout setup: ~/.claude/skills/loci-save -> <repo>/src/loci/
    skills/loci-save. Overwriting it with a copy would take away the live
    editing the developer set it up for, so it is left alone unless forced.
    """
    if not dest.is_symlink():
        return False
    try:
        return dest.resolve() == source.resolve()
    except OSError:
        return False


def plan(
    skills_root: Path | None = None,
    source: Path | None = None,
    force: bool = False,
) -> list[SkillStatus]:
    """Work out what installing would do, without touching anything."""
    skills_root = DEFAULT_SKILLS_ROOT if skills_root is None else skills_root
    statuses = []
    for skill_source in packaged_skills(source):
        name = skill_source.name
        dest = skills_root / name
        packaged = read_skill_version(skill_source / "SKILL.md")
        installed = read_skill_version(dest / "SKILL.md") if dest.exists() else None

        if _links_into_package(dest, skill_source) and not force:
            action = LINKED
        elif not dest.exists():
            action = INSTALL
        elif installed is None or packaged is None:
            # An unparseable version on either side is not a reason to leave a
            # skill stale — reinstalling restores a known state.
            action = UPDATE
        elif installed > packaged and not force:
            action = AHEAD
        elif installed == packaged and not force:
            action = CURRENT
        else:
            action = UPDATE

        statuses.append(SkillStatus(name, skill_source, dest, packaged, installed, action))

    if not statuses:
        # Nothing packaged means nothing to compare against, and every
        # installed skill would look like an orphan. That is the failure the
        # package move caused once already, in the other direction: an
        # installer that removes the user's skills before discovering it has
        # nothing to put back.
        return statuses

    packaged_names = {s.name for s in statuses}
    return statuses + _orphans(skills_root, packaged_names, _source_root(source))


def uninstall(status: SkillStatus) -> None:
    """Take one skill out of the skills directory."""
    if status.dest.is_symlink():
        status.dest.unlink()
    elif status.dest.is_dir():
        shutil.rmtree(status.dest)
    elif status.dest.exists():
        status.dest.unlink()


def install(status: SkillStatus, link: bool = False) -> None:
    """Put one skill in place, replacing whatever is there."""
    assert status.source is not None, "install() called on a removal"
    status.dest.parent.mkdir(parents=True, exist_ok=True)

    # is_symlink() first: a symlink to a directory answers True to is_dir(),
    # and rmtree on it raises rather than removing the link.
    if status.dest.is_symlink():
        status.dest.unlink()
    elif status.dest.is_dir():
        shutil.rmtree(status.dest)
    elif status.dest.exists():
        status.dest.unlink()

    if link:
        status.dest.symlink_to(status.source)
    else:
        # The whole directory, not just SKILL.md, so a skill that grows a
        # reference file or a script gets it installed too.
        shutil.copytree(status.source, status.dest)


def apply(statuses: list[SkillStatus], link: bool = False) -> list[SkillStatus]:
    """Install every status that calls for it. Returns the ones written."""
    written = [s for s in statuses if s.writes]
    for status in written:
        if status.action == REMOVE:
            uninstall(status)
        else:
            install(status, link=link)
    return written


def install_all(
    skills_root: Path | None = None,
    source: Path | None = None,
    link: bool = False,
    force: bool = False,
) -> list[SkillStatus]:
    """Plan and apply in one call — the entry point for setup scripts."""
    return apply(plan(skills_root, source, force=force), link=link)


def _format_version(value: int | None) -> str:
    return "—" if value is None else f"v{value}"


def _render(statuses: list[SkillStatus], skills_root: Path) -> str:
    """The table the user reads before deciding."""
    if not statuses:
        return f"No skills found in {SKILLS_SOURCE} — nothing to install."

    width = max(len(s.name) for s in statuses)
    lines = [f"Loci skills → {skills_root}", ""]
    for s in statuses:
        if s.action in (INSTALL, UPDATE):
            versions = f"{_format_version(s.installed_version)} → {_format_version(s.packaged_version)}"
        elif s.action == REMOVE:
            versions = f"{_format_version(s.installed_version)} → —"
        else:
            versions = _format_version(s.installed_version)
        lines.append(f"  {s.name:<{width}}  {versions:<12}  {s.action}")
    return "\n".join(lines)


def _summary(statuses: list[SkillStatus]) -> str:
    installs = sum(1 for s in statuses if s.action == INSTALL)
    updates = sum(1 for s in statuses if s.action == UPDATE)
    removals = sum(1 for s in statuses if s.action == REMOVE)
    parts = []
    if installs:
        parts.append(f"{installs} to install")
    if updates:
        parts.append(f"{updates} to update")
    if removals:
        parts.append(f"{removals} to remove")
    return ", ".join(parts) if parts else "Everything is up to date."


def run(argv: list[str] | None = None, stdin=None, stdout=None) -> int:
    """`loci skills`. Returns the process exit code."""
    out = stdout if stdout is not None else sys.stdout
    stream = stdin if stdin is not None else sys.stdin

    parser = build_parser()
    args = parser.parse_args(argv)
    skills_root = Path(args.dir).expanduser() if args.dir else DEFAULT_SKILLS_ROOT

    statuses = plan(skills_root, force=args.force)
    print(_render(statuses, skills_root), file=out)
    print("", file=out)

    pending = [s for s in statuses if s.writes]
    if not pending:
        print(_summary(statuses), file=out)
        return 0

    print(_summary(statuses), file=out)
    if not args.yes:
        # A non-interactive run that would write is refused rather than assumed:
        # this replaces files in the user's Claude Code config.
        if not hasattr(stream, "isatty") or not stream.isatty():
            print("Not a terminal — re-run with --yes to install without asking.", file=out)
            return 1
        print("Proceed? [y/N] ", end="", file=out, flush=True)
        if stream.readline().strip().lower() not in ("y", "yes"):
            print("Nothing written.", file=out)
            return 1

    written = apply(statuses, link=args.link)
    print("", file=out)
    for status in written:
        print(f"  {status.action}: {status.dest}", file=out)
    print("\nRestart Claude Code to pick up the change.", file=out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loci skills",
        description="Install or update the Loci skills in Claude Code.",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help=f"Skills directory to install into (default: {DEFAULT_SKILLS_ROOT}).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Install without asking. Required when stdin is not a terminal.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Reinstall even skills that are current, newer, or dev symlinks.",
    )
    parser.add_argument(
        "--link", action="store_true",
        help="Symlink instead of copying. Only sensible from a checkout.",
    )
    return parser

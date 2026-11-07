"""
Install the Loci skill stubs into an agent's skills directory.

The agents are listed in clients.py (Claude Code, Hermes). The rest of this
docstring says "Claude Code" because that was the first; the mechanism is the
same for each. This is how an agent learns the skills exist. Each packaged skill
(`loci/skills/<name>/SKILL.md`) is the procedure the MCP server serves through
`read_skill`, assembled with the user's own additions from the vault (see
skill_assembly.py). What goes into `~/.claude/skills/<name>/SKILL.md` is not
that file but a stub generated from it: the same frontmatter — name and the
trigger description Claude Code matches on — over a body that says "call
`read_skill` and follow what it returns".

A stub, not a copy, because a copy would run. The previous design installed
the whole procedure and opened it with a version check that deferred to the
server only when the packaged number had moved; whenever the numbers matched,
the local copy ran on its own and anything the server had composed — the
user's overlay above all — was never seen. The stub cannot run on its own, so
the assembled skill is the only one there is.

Two consequences. A change to the procedure needs no reinstall — the server
reads the file on every call — so this command only has work to do when a
stub itself would change: a new or removed skill, or a reworded trigger
description. And there is no longer any reason to symlink: a link into the
package would hand Claude Code the procedure directly, which is the exact
failure the stub exists to prevent, so a symlink found at the destination is
replaced like any other stale install.

What is no longer packaged is also taken out. A skill renamed or dropped
upstream would otherwise sit in ~/.claude/skills/ forever with Claude Code
still loading it — beside its replacement, in the rename case. Only entries
this installer could have created are ever removed; see _orphans().
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from loci import clients as clients_mod
from loci.clients import CLAUDE, Client
from loci.skill_assembly import split_frontmatter

# The skills live beside this module, inside the package. Not a repo path:
# this resolves to site-packages on an installed copy, which is the point.
SKILLS_SOURCE = Path(__file__).parent / "skills"

# references/ sits under skills/ but is not a skill — it holds the canonical
# ontology and relation YAML the registries read and vault_init seeds. Copying
# it into ~/.claude/skills/ would present it to Claude Code as a broken skill.
NOT_SKILLS = frozenset({"references"})

DEFAULT_SKILLS_ROOT = Path.home() / ".claude" / "skills"

# Every skill Loci ships is named this way, and it is the only marker a stub
# directory carries once it is out of the package. See _orphans().
SKILL_NAME_PREFIX = clients_mod.SKILL_NAME_PREFIX

# What to do with each skill. Only INSTALL, UPDATE and REMOVE write anything.
INSTALL = "install"
UPDATE = "update"
CURRENT = "up to date"
REMOVE = "removed — no longer shipped"

_STUB_BODY = """
# {name}

This file is a stub. The skill itself is assembled by the Loci MCP server from
the packaged procedure and your own additions kept in the vault, so the copy
here never goes stale and never needs reinstalling.

Call `{read_skill}(skill="{name}")` and follow what it returns for the whole
interaction.

If the call is unavailable or errors, tell the user the Loci vault is not
reachable, relay the tool's error text verbatim (it names the cause and the fix
for this install), and stop. If there is no error text, the MCP server itself is
not connected — the user needs to check their MCP client config and restart
{restart}.
"""


@dataclass(frozen=True)
class SkillStatus:
    """One skill's source, destination, and what to do.

    `source` is None for a REMOVE: the skill is only in the destination, which
    is the whole reason it is being taken out.
    """

    name: str
    source: Path | None
    dest: Path
    action: str
    client: Client = CLAUDE

    @property
    def writes(self) -> bool:
        return self.action in (INSTALL, UPDATE, REMOVE)


def stub(name: str, skill_md: str, client: Client = CLAUDE) -> str:
    """The SKILL.md Claude Code gets, built from the packaged skill's frontmatter.

    The frontmatter is carried over verbatim: `name` and `description` are what
    Claude Code reads to decide when the skill applies, and they have to say
    exactly what the packaged skill says.
    """
    frontmatter, _ = split_frontmatter(skill_md)
    return frontmatter + _STUB_BODY.format(
        name=name, read_skill=client.read_skill_tool, restart=client.restart
    )


def packaged_stub(skill_source: Path, client: Client = CLAUDE) -> str:
    return stub(skill_source.name, (skill_source / "SKILL.md").read_text(encoding="utf-8"), client)


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

    That is the old checkout setup, and the one shape of destination this
    installer can be sure it made. resolve() answers for a dangling link too —
    a skill renamed or dropped — which is exactly the case _orphans() needs.
    """
    if not dest.is_symlink():
        return False
    try:
        return dest.resolve().is_relative_to(source_root.resolve())
    except OSError:
        return False


def _installed_text(dest: Path) -> str | None:
    """What is at the destination now, or None if nothing readable is."""
    try:
        return (dest / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None


def _orphans(
    skills_root: Path, packaged: set[str], source_root: Path, client: Client = CLAUDE
) -> list[SkillStatus]:
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
        stale.append(SkillStatus(dest.name, None, dest, REMOVE, client))
    return stale


def plan(
    skills_root: Path | None = None,
    source: Path | None = None,
    client: Client = CLAUDE,
) -> list[SkillStatus]:
    """Work out what installing would do, without touching anything."""
    skills_root = DEFAULT_SKILLS_ROOT if skills_root is None else skills_root
    statuses = []
    for skill_source in packaged_skills(source):
        name = skill_source.name
        dest = skills_root / name

        if not dest.exists() and not dest.is_symlink():
            action = INSTALL
        elif dest.is_symlink():
            # Whatever it points at, it is not a stub: a link into the package
            # serves the procedure directly, and a link anywhere else is not
            # ours to trust. Either way the stub goes in its place.
            action = UPDATE
        elif _installed_text(dest) == packaged_stub(skill_source, client):
            action = CURRENT
        else:
            action = UPDATE

        statuses.append(SkillStatus(name, skill_source, dest, action, client))

    if not statuses:
        # Nothing packaged means nothing to compare against, and every
        # installed skill would look like an orphan. That is the failure the
        # package move caused once already, in the other direction: an
        # installer that removes the user's skills before discovering it has
        # nothing to put back.
        return statuses

    packaged_names = {s.name for s in statuses}
    return statuses + _orphans(skills_root, packaged_names, _source_root(source), client)


def _clear(dest: Path) -> None:
    # is_symlink() first: a symlink to a directory answers True to is_dir(),
    # and rmtree on it raises rather than removing the link.
    if dest.is_symlink():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()


def uninstall(status: SkillStatus) -> None:
    """Take one skill out of the skills directory."""
    _clear(status.dest)


def install(status: SkillStatus) -> None:
    """Put one stub in place, replacing whatever is there."""
    assert status.source is not None, "install() called on a removal"
    status.dest.parent.mkdir(parents=True, exist_ok=True)
    _clear(status.dest)
    status.dest.mkdir()
    (status.dest / "SKILL.md").write_text(
        packaged_stub(status.source, status.client), encoding="utf-8"
    )


def apply(statuses: list[SkillStatus]) -> list[SkillStatus]:
    """Install every status that calls for it. Returns the ones written."""
    written = [s for s in statuses if s.writes]
    for status in written:
        if status.action == REMOVE:
            uninstall(status)
        else:
            install(status)
    return written


def install_all(
    skills_root: Path | None = None, source: Path | None = None, client: Client = CLAUDE
) -> list[SkillStatus]:
    """Plan and apply in one call — the entry point for setup scripts."""
    return apply(plan(skills_root, source, client))


def refresh_installed() -> list[SkillStatus]:
    """Bring the stubs of every agent that already has Loci up to date.

    Called by `loci-mcp` on startup, which is how a `uv tool upgrade` reaches
    the stubs: PyPI installs have no post-install hook, and the next time the
    agent starts the server this runs. Agents without Loci stubs are never
    enrolled here, and nothing is printed (stdout is the MCP protocol).
    Opt out with LOCI_SKIP_SKILL_REFRESH=1.
    """
    import os

    if os.environ.get("LOCI_SKIP_SKILL_REFRESH") == "1":
        return []
    written: list[SkillStatus] = []
    for client in clients_mod.installed():
        try:
            written += install_all(client.skills_root(), client=client)
        except OSError:
            continue
    return written


def _render(statuses: list[SkillStatus], skills_root: Path, label: str = "Loci skills") -> str:
    """The table the user reads before deciding."""
    if not statuses:
        return f"No skills found in {SKILLS_SOURCE} — nothing to install."

    width = max(len(s.name) for s in statuses)
    lines = [f"{label} → {skills_root}", ""]
    for s in statuses:
        lines.append(f"  {s.name:<{width}}  {s.action}")
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

    # --dir is one explicit folder (Codex and friends) and is written in the
    # Claude Code stub style, as it always was. Otherwise the agents come from
    # --target, or from detection — see clients.resolve_targets.
    if args.dir:
        destinations = [(CLAUDE, Path(args.dir).expanduser())]
    else:
        try:
            targets = clients_mod.resolve_targets(args.target, stream, out)
        except clients_mod.TargetError as e:
            print(str(e), file=out)
            return 1
        destinations = [(c, c.skills_root()) for c in targets]

    plans = []
    for client, root in destinations:
        statuses = plan(root, client=client)
        plans.append((client, root, statuses))
        print(_render(statuses, root, f"Loci skills ({client.label})"), file=out)
        print(_summary(statuses), file=out)
        print("", file=out)

    pending = any(s.writes for _, _, statuses in plans for s in statuses)
    if not pending:
        return 0

    if not args.yes:
        # A non-interactive run that would write is refused rather than assumed:
        # this replaces files in the user's agent config.
        if not hasattr(stream, "isatty") or not stream.isatty():
            print("Not a terminal — re-run with --yes to install without asking.", file=out)
            return 1
        print("Proceed? [y/N] ", end="", file=out, flush=True)
        if stream.readline().strip().lower() not in ("y", "yes"):
            print("Nothing written.", file=out)
            return 1

    for client, _root, statuses in plans:
        written = apply(statuses)
        if not written:
            continue
        for status in written:
            print(f"  {status.action}: {status.dest}", file=out)
        print(f"\nRestart {client.restart} to pick up the change.", file=out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loci skills",
        description="Install or update the Loci skill stubs in your agent (Claude Code, Hermes).",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="claude, hermes, a comma-separated list, or all. With none given, "
        "a single detected agent is used and several are asked about.",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="Install into this skills directory instead (for an agent not listed).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Install without asking. Required when stdin is not a terminal.",
    )
    return parser

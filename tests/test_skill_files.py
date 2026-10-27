"""
Guards on the shipped SKILL.md files themselves.

The skills are prose the model follows verbatim, so a stale command in one is a
user-visible bug that no amount of Python coverage reaches: the model reads
`python setup.py` out of the file and tells the user to run it.
"""
import inspect
import re
from pathlib import Path

import pytest

from loci import api, mcp_server, skill_assembly

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "src" / "loci" / "skills"

SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))

# Invocations that no longer exist after the package move. The value is what to
# use instead, so a failure says what to write rather than only what is wrong.
REMOVED_COMMANDS = {
    "python setup.py": "uv run setup.py",
    "python tools/vault_init.py": "the set_vault_root tool (see NOT_CONFIGURED_MESSAGE)",
    "loci_mcp/server.py": "loci-mcp",
    "server/http_server.py": "loci.http_server",
    "loci-skill/": "src/loci/skills/",
}

# Where a stale command is a bug: prose and code a user or the model acts on.
# The skills are the sharp end, but the same commands were left behind in the
# README, the design copy spec, and setup.py's own usage line, none of which the
# skills glob reaches.
SEARCHED_SUFFIXES = {".md", ".py"}
SEARCHED_ROOTS = [
    REPO_ROOT / "src",
    REPO_ROOT / "docs",
    REPO_ROOT / "app" / "design",
    REPO_ROOT / "tests",
]
SEARCHED_TOP_LEVEL_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "setup.py",
]

# This file has to name the removed commands to test for them.
EXEMPT = {Path(__file__).resolve()}


def _searched_files() -> list[Path]:
    found = [p for p in SEARCHED_TOP_LEVEL_FILES if p.exists()]
    for root in SEARCHED_ROOTS:
        if not root.is_dir():
            continue
        found += [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix in SEARCHED_SUFFIXES
            and "node_modules" not in p.parts
        ]
    return sorted(set(found) - EXEMPT)


SEARCHED_FILES = _searched_files()


def _frontmatter(text: str) -> str:
    """
    The frontmatter block only, so a `skill_version:` shown as an example inside
    the body is not mistaken for the file's own declaration.
    """
    if not text.startswith("---"):
        return ""
    return text.split("\n---", 1)[0]


def test_there_are_skill_files_to_check():
    """A bad glob would make every test below vacuously pass."""
    assert SKILL_FILES, f"no SKILL.md found under {SKILLS_DIR}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_carries_no_version_check(skill):
    """
    The version check was how a local copy decided whether to defer to the
    server: whenever the numbers matched it ran on its own, and anything the
    server composed — the user's overlay — was never seen. The local copy is
    a stub now (skills_install.py) and the server serves every procedure
    live, so a version has nothing to compare against and a check would only
    invite the model to skip the assembled document it was already given.
    """
    text = skill.read_text(encoding="utf-8")
    assert "skill_version" not in text, f"{skill.parent.name} still declares a skill_version"
    assert "Version Check" not in text, f"{skill.parent.name} still carries a version check"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_frontmatter_is_only_what_the_stub_needs(skill):
    """
    The stub copies the frontmatter verbatim, so it is the one part of a
    skill that reaches ~/.claude/skills/ — and a key added here ships to every
    install and stays until the next `loci skills`. Keep it to what Claude
    Code reads to trigger the skill.
    """
    frontmatter, _ = skill_assembly.split_frontmatter(skill.read_text(encoding="utf-8"))
    assert frontmatter, f"{skill.parent.name} has no frontmatter — Claude Code needs name and description"
    keys = re.findall(r"^([a-z_]+):", frontmatter, re.MULTILINE)
    assert keys == ["name", "description"], f"{skill.parent.name} frontmatter keys: {keys}"
    assert f"name: {skill.parent.name}\n" in frontmatter


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_protects_at_least_one_section(skill):
    """
    The overlay contract is "the user's additions win, except under 🔒". A
    procedure with no 🔒 heading has handed the user every rule it has —
    including "ask before writing" — which is not what the marker is for.
    """
    text = skill.read_text(encoding="utf-8")
    protected = [
        line for line in text.splitlines()
        if line.startswith("#") and skill_assembly.PROTECTED in line
    ]
    assert protected, f"{skill.parent.name} marks no heading with {skill_assembly.PROTECTED}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_an_overlay_seed(skill):
    """
    Every packaged skill needs its `<name>-user.md` in references/ — that is
    what vault_init seeds, and what read_skill falls back to for a vault seeded
    before the overlay existed. A skill without one reads as having no
    additions at all, silently.
    """
    from loci.tools.vault_init import USER_SKILL_OVERLAYS

    slug = skill.parent.name
    name = skill_assembly.seed_filename(slug)
    assert (SKILLS_DIR / "references" / name).is_file(), f"missing references/{name}"
    assert slug in USER_SKILL_OVERLAYS, (
        f"{slug} is not seeded — add it to USER_SKILL_OVERLAYS"
    )


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_no_skill_names_a_command_that_was_removed(skill):
    """
    These paths went away when Loci became an installable package. A skill that
    still names one hands the user a command that fails.
    """
    text = skill.read_text(encoding="utf-8")
    for removed, replacement in REMOVED_COMMANDS.items():
        assert removed not in text, (
            f"{skill.parent.name} still names `{removed}` — use `{replacement}`"
        )


# `read_skill` defaults to this skill, and the stub always passes the name
# explicitly — the default only matters when a caller drops the argument.
READ_SKILL_DEFAULT = "loci-save"


def test_read_skill_default_names_a_skill_that_exists():
    """
    Renaming the loci-save directory satisfies every other guard while leaving
    the code default pointing at a path that is gone, so `loci__read_skill`
    with no argument raises FileNotFoundError with the suite still green.
    """
    assert (SKILLS_DIR / READ_SKILL_DEFAULT / "SKILL.md").exists(), (
        f"read_skill defaults to {READ_SKILL_DEFAULT!r}, but "
        f"src/loci/skills/{READ_SKILL_DEFAULT}/SKILL.md does not exist — "
        "point the default at a skill that ships"
    )


@pytest.mark.parametrize(
    "func", [api.read_skill, mcp_server.read_skill], ids=["api", "mcp_server"]
)
def test_read_skill_default_is_a_skill_that_ships(func):
    param = inspect.signature(func).parameters.get("skill")
    default = param.default if param else "<no `skill` parameter>"
    assert default == READ_SKILL_DEFAULT, (
        f"{func.__module__}.read_skill now defaults to {default!r}; "
        "keep it in step with READ_SKILL_DEFAULT above"
    )


def test_the_removed_command_search_covers_something():
    """A bad root list would make the repo-wide guard vacuously pass."""
    assert len(SEARCHED_FILES) > 20, f"only {len(SEARCHED_FILES)} files searched"
    assert (REPO_ROOT / "README.md") in SEARCHED_FILES
    # Naming the roots that carry prose, so dropping one fails here rather than
    # leaving the guard quietly green over a directory it no longer reads.
    for root in (REPO_ROOT / "src", REPO_ROOT / "docs", REPO_ROOT / "tests",
                 REPO_ROOT / "app" / "design"):
        assert any(root in p.parents for p in SEARCHED_FILES), f"nothing searched under {root}"


@pytest.mark.parametrize(
    "path", SEARCHED_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_prose_or_script_names_a_command_that_was_removed(path):
    """
    Wider than the skills glob on purpose. `python setup.py` outlived the
    package move in setup.py's own usage line and in the UI error-copy spec,
    where the skills test could not see it — and copy in a spec is what the next
    error message gets written from.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    for removed, replacement in REMOVED_COMMANDS.items():
        assert removed not in text, (
            f"{path.relative_to(REPO_ROOT)} still names `{removed}` — "
            f"use `{replacement}`"
        )


# ---------------------------------------------------------------------------
# Size and tool-surface guards
# ---------------------------------------------------------------------------

# A skill is a procedure the model has to hold in its head for a whole
# interaction. loci-save reached 790 lines and the model skimmed it — a real
# save on 2026-09-10 skipped the link-scan step and wrote a meeting note
# without checking for the entity it named. Knowledge belongs in reference
# files read on demand (`read_meta`), deterministic steps belong in tools;
# only the procedure belongs here. Raise this number deliberately, not to
# make a failure go away.
MAX_SKILL_LINES = 300

TOOL_CALL = re.compile(r"`loci__([a-z_]+)")
META_READ = re.compile(r'loci__read_meta\(file="([a-z-]+)"\)')


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_stays_short_enough_to_be_followed(skill):
    lines = len(skill.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_SKILL_LINES, (
        f"{skill.parent.name}/SKILL.md is {lines} lines (cap {MAX_SKILL_LINES}). "
        "Move knowledge into a reference file served by read_meta, or a "
        "deterministic step into a tool, rather than raising the cap."
    )


def _registered_tool_names() -> set[str]:
    return {t.name for t in mcp_server.mcp._tool_manager.list_tools()}


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_tool_a_skill_names_is_registered(skill):
    """
    The skill ↔ tool sync rule, enforced: a skill that names a tool the server
    does not register sends the model to a call that fails.
    """
    named = set(TOOL_CALL.findall(skill.read_text(encoding="utf-8")))
    unknown = sorted(named - _registered_tool_names())
    assert not unknown, f"{skill.parent.name} names tools that do not exist: {unknown}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_meta_key_a_skill_reads_exists(skill, tmp_vault):
    """
    The other half of the sync rule: every `read_meta(file=...)` a skill
    spells out has to be a key api.read_meta answers — the reference files
    lifted out of loci-save are only reachable through it.
    """
    keys = set(META_READ.findall(skill.read_text(encoding="utf-8")))
    if not keys:
        pytest.skip("reads no meta file")
    for key in sorted(keys):
        assert api.read_meta(key).strip(), f"{skill.parent.name} reads unknown meta key {key!r}"

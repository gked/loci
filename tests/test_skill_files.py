"""
Guards on the shipped SKILL.md files themselves.

The skills are prose the model follows verbatim, so a stale command in one is a
user-visible bug that no amount of Python coverage reaches: the model reads
`python setup.py` out of the file and tells the user to run it.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "src" / "loci" / "skills"

SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))

FRONTMATTER_VERSION = re.compile(r"^skill_version:\s*(\d+)\s*$", re.MULTILINE)
BODY_VERSION = re.compile(r"This skill is at `skill_version: (\d+)`\.")

# Invocations that no longer exist after the package move. The value is what to
# use instead, so a failure says what to write rather than only what is wrong.
REMOVED_COMMANDS = {
    "python setup.py": "uv run setup.py",
    "loci_mcp/server.py": "loci-mcp",
    "server/http_server.py": "loci.http_server",
}

# Where a stale command is a bug: prose and code a user or the model acts on.
# The skills are the sharp end, but the same commands were left behind in the
# README, the design copy spec, and setup.py's own usage line, none of which the
# skills glob reaches.
SEARCHED_SUFFIXES = {".md", ".py"}
SEARCHED_ROOTS = [
    REPO_ROOT / "src",
    REPO_ROOT / "app" / "design",
    REPO_ROOT / "tests",
    REPO_ROOT / "deploy",
]
SEARCHED_TOP_LEVEL_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "setup.py",
    REPO_ROOT / "setup_docker.py",
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
def test_frontmatter_and_body_versions_agree(skill):
    """
    A skill states its version twice — once in frontmatter, once in the body
    line the version check reads. Bumping one and not the other leaves the
    deployed copy claiming a version it does not have, and the check that is
    supposed to catch a stale deploy silently stops working.
    """
    text = skill.read_text(encoding="utf-8")
    frontmatter = FRONTMATTER_VERSION.search(_frontmatter(text))
    body = BODY_VERSION.search(text)

    if frontmatter is None and body is None:
        pytest.skip(f"{skill.parent.name} is not versioned")

    assert frontmatter is not None, f"{skill.parent.name}: body states a version, frontmatter does not"
    assert body is not None, f"{skill.parent.name}: frontmatter states a version, body does not"
    assert frontmatter.group(1) == body.group(1), (
        f"{skill.parent.name}: frontmatter says {frontmatter.group(1)}, "
        f"body says {body.group(1)} — both have to be bumped together"
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


def test_the_removed_command_search_covers_something():
    """A bad root list would make the repo-wide guard vacuously pass."""
    assert len(SEARCHED_FILES) > 20, f"only {len(SEARCHED_FILES)} files searched"
    assert (REPO_ROOT / "README.md") in SEARCHED_FILES


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

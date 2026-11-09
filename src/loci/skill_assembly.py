"""
Assemble a skill from the packaged procedure and the user's own additions.

A skill has two halves. The packaged half is `loci/skills/<name>/SKILL.md`,
the procedure Loci ships and tests. The user's half is one Markdown file per
skill in the vault, `vault/skills/<name>.md`, seeded once from the stub in
`skills/references/` and never overwritten by an upgrade. `read_skill` returns
the two joined, with a preamble that says how they combine: the user's file
wins wherever it disagrees with the packaged procedure, except under headings
marked 🔒, which hold regardless.

The copy Claude Code loads from ~/.claude/skills/ is a stub that does nothing
but call `read_skill` (see skills_install.py). That is what makes the overlay
reachable at all: a skill that ran from its local copy would never see the
user's file, and the previous design — a full local copy with a version check
that only deferred to the server when the number moved — was exactly that. An
edit to the packaged procedure is live the moment the MCP server reads it;
nothing has to be reinstalled.
"""

from __future__ import annotations

from pathlib import Path

from loci.language import DEFAULT_LANGUAGE

SKILLS_DIR = Path(__file__).parent / "skills"
REFERENCES_DIR = SKILLS_DIR / "references"

# The overlay's name in references/. The seed keeps the `-user` suffix because
# it sits beside the canonical meta files there and would otherwise read as one
# of them; in the vault the directory already says whose the file is.
SEED_SUFFIX = "-user.md"

# Where the user's half of every skill lives, relative to the vault root.
# Before META_VERSION 14 these sat in `meta/` under their seed name — see
# legacy_overlay_path(), which the vault upgrade uses to move them.
OVERLAY_DIR = "skills"

# The marker on a heading in the packaged procedure that the user's additions
# cannot override. Prose, not enforcement: the preamble tells the model how to
# treat it, and test_skill_files.py checks the procedures actually use it.
PROTECTED = "🔒"

OVERLAY_HEADING = "Your additions"


def canonical_path(skill: str, language: str | None = None) -> Path:
    """The packaged SKILL.md for a skill; FileNotFoundError if it does not ship.

    With a language other than English, the translation `SKILL.<language>.md`
    beside it when there is one; a skill not translated yet serves the English
    procedure rather than failing.
    """
    p = SKILLS_DIR / skill / "SKILL.md"
    if not p.is_file():
        raise FileNotFoundError(f"Skill file not found: {p}")
    if language and language != DEFAULT_LANGUAGE:
        localized = p.with_name(f"SKILL.{language}.md")
        if localized.is_file():
            return localized
    return p


def seed_filename(skill: str) -> str:
    """The overlay seed's name in references/."""
    return f"{skill}{SEED_SUFFIX}"


def overlay_filename(skill: str) -> str:
    """The overlay's name inside the vault."""
    return f"{skill}.md"


def overlay_path(vault_root: Path, skill: str) -> Path:
    return vault_root / OVERLAY_DIR / overlay_filename(skill)


def legacy_overlay_path(vault_root: Path, skill: str) -> Path:
    """Where the overlay lived before META_VERSION 14.

    Only the vault upgrade reads this — everything else goes through
    overlay_path(). A vault that has been upgraded no longer has the file.
    """
    return vault_root / "meta" / seed_filename(skill)


def overlay_display(skill: str) -> str:
    """How the overlay's location is named to the model, in prose."""
    return f"`vault/{OVERLAY_DIR}/{overlay_filename(skill)}`"


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter block including its `---` fences, body after it).

    A file with no frontmatter is all body. The fences are kept on the
    frontmatter so a caller can write it back out verbatim — the stub
    generator does, so Claude Code sees the same name and trigger description
    the packaged skill declares.
    """
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[: end + len("\n---\n")], text[end + len("\n---\n"):]


def read_overlay(vault_root: Path | None, skill: str) -> tuple[str, bool] | None:
    """(the user's additions for a skill, whether they came from the vault),
    or None when there is no vault to hold them.

    A vault seeded before the overlay existed falls back to the packaged seed,
    the same way read_meta does for any meta file that has not been seeded yet.
    The flag is False on that path so assemble() can label the fallback as what
    it is: an unreachable or unseeded vault file reads the same as an empty
    one, and the model should not report "no rules" off the back of the seed.
    """
    if vault_root is None:
        return None
    p = overlay_path(vault_root, skill)
    if p.exists():
        return p.read_text(encoding="utf-8"), True
    p = REFERENCES_DIR / seed_filename(skill)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8"), False


def _preamble(skill: str, language: str | None = None) -> str:
    if language == "ru-RU":
        return (
            f"# {skill}\n\n"
            "Следуйте этому документу на протяжении всего взаимодействия. В нём две "
            "части: поставляемая процедура, затем **Your additions** — правила "
            f"пользователя из {overlay_display(skill)}. Если части расходятся, "
            f"приоритет у дополнений пользователя, кроме заголовков с меткой {PROTECTED}: "
            "они действуют при любых дополнениях. Чтобы изменить дополнения, вызовите "
            f'`loci__write_skill(skill="{skill}", content=...)` — `content` **заменяет** '
            "весь файл, поэтому передайте `append=True`, чтобы добавить правило и сохранить "
            "прежние. Поставляемая процедура отсюда не редактируется. Инструменты ниже "
            "записаны как `loci__<tool>`; ваш клиент может показывать тот же инструмент "
            "как `mcp__loci__<tool>` или `mcp_loci_<tool>`.\n"
        )
    return (
        f"# {skill}\n\n"
        "Follow this document for the whole interaction. It has two parts: the "
        "packaged procedure, then **Your additions** — the rules the user keeps in "
        f"{overlay_display(skill)}. Where the two disagree, the user's "
        f"additions win, except under headings marked {PROTECTED}: those hold no "
        "matter what the additions say. To change the additions, call "
        f'`loci__write_skill(skill="{skill}", content=...)` — `content` **replaces** '
        "the whole file, so pass `append=True` to add a rule and keep the ones "
        "already there. The packaged procedure is not editable from here. Tools "
        "are written `loci__<tool>` below; your client may show the same tool as "
        "`mcp__loci__<tool>` or `mcp_loci_<tool>`.\n"
    )


def assemble(skill: str, vault_root: Path | None, language: str | None = None) -> str:
    """The text `read_skill` returns: preamble, packaged procedure, user additions."""
    path = canonical_path(skill, language)
    _, body = split_frontmatter(path.read_text(encoding="utf-8"))
    overlay = read_overlay(vault_root, skill)
    # The preamble follows the procedure actually served, not the setting: a
    # skill with no translation yet is English all the way through.
    served = language if path.name != "SKILL.md" else None

    parts = [_preamble(skill, served), "---\n", body.strip("\n") + "\n", "---\n"]
    if overlay is None:
        parts.append(
            f"# {OVERLAY_HEADING}\n\n"
            "_No vault is configured yet, so the user's additions could not be "
            "loaded. They apply from the next call once `loci__set_vault_root` "
            "has run._\n"
        )
    else:
        text, from_vault = overlay
        where = overlay_display(skill)
        if not from_vault:
            where = (
                f"packaged default — {where} is not in the vault yet, so the "
                "user may have rules that could not be loaded"
            )
        parts.append(f"# {OVERLAY_HEADING} ({where})\n\n" + text.strip("\n") + "\n")
    return "\n".join(parts)


def write_overlay(vault_root: Path, skill: str, content: str, append: bool = False) -> Path:
    """Write the user's additions for a skill. Returns the path written.

    The packaged procedure is never touched: canonical_path() is called only so
    an unknown skill name fails the same way read_skill does, rather than
    creating an overlay nothing will ever read.
    """
    canonical_path(skill)
    p = overlay_path(vault_root, skill)
    p.parent.mkdir(parents=True, exist_ok=True)
    if append:
        # read_overlay, not p.read_text: a vault that predates the overlay has
        # only the packaged stub, and an append should land under its header.
        existing = (read_overlay(vault_root, skill) or ("", False))[0]
        if existing and not existing.endswith("\n"):
            existing += "\n"
        content = existing + "\n" + content
    p.write_text(content, encoding="utf-8")
    return p

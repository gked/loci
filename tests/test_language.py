"""
The `language` setting: where it comes from, what it changes, what it must not.

It changes prose only. The procedure a model follows is translated; the names
it and the tools match on (tool names, frontmatter fields, the skill
frontmatter the host agent triggers on, the 🔒 headings) are not.
"""

import re
from pathlib import Path

import pytest

from loci import api, skill_assembly
from loci.language import ENV_VAR, get_language, normalize

SKILLS = ["loci-save", "loci-query", "loci-inbox", "loci-ingest-directory"]
SKILLS_DIR = Path(skill_assembly.SKILLS_DIR)


@pytest.fixture(autouse=True)
def _no_language_env(monkeypatch, tmp_path):
    """Neither the developer's env nor their real config.yml may leak in."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "no-config.yml"))


def _headings(text: str) -> list[tuple[int, bool]]:
    """(level, protected) for each heading outside code fences."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := re.match(r"(#{1,6}) ", line)):
            out.append((len(m.group(1)), skill_assembly.PROTECTED in line))
    return out


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("ru", "ru-RU"), ("ru_RU", "ru-RU"), ("RU-ru", "ru-RU"), (" ru-RU ", "ru-RU"),
    ("en", "en"), ("en-US", "en"),
    ("de", None), ("", None), (None, None), (5, None),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_default_is_english():
    assert get_language() == "en"


def test_env_var_selects_the_language(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "ru")
    assert get_language() == "ru-RU"


def test_config_file_selects_the_language(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yml"
    cfg.write_text("vault_root: /x\nlanguage: ru-RU\n")
    monkeypatch.setenv("LOCI_CONFIG", str(cfg))
    assert get_language() == "ru-RU"


def test_env_var_wins_over_the_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yml"
    cfg.write_text("language: ru-RU\n")
    monkeypatch.setenv("LOCI_CONFIG", str(cfg))
    monkeypatch.setenv(ENV_VAR, "en")
    assert get_language() == "en"


def test_config_file_is_read_even_with_vault_root_in_the_environment(monkeypatch, tmp_path):
    """load_config() returns only the vault root in that mode; the key must survive."""
    cfg = tmp_path / "config.yml"
    cfg.write_text("language: ru-RU\n")
    monkeypatch.setenv("LOCI_CONFIG", str(cfg))
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(tmp_path))
    assert get_language() == "ru-RU"


@pytest.mark.parametrize("body", ["language: klingon\n", "language: [unclosed\n", "- a\n- b\n"])
def test_a_bad_value_or_file_falls_back_to_english(monkeypatch, tmp_path, body):
    cfg = tmp_path / "config.yml"
    cfg.write_text(body)
    monkeypatch.setenv("LOCI_CONFIG", str(cfg))
    assert get_language() == "en"


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_has_a_russian_procedure(skill):
    assert (SKILLS_DIR / skill / "SKILL.ru-RU.md").is_file()


@pytest.mark.parametrize("skill", SKILLS)
def test_translation_keeps_the_frontmatter_and_the_protected_headings(skill):
    en = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    ru = (SKILLS_DIR / skill / "SKILL.ru-RU.md").read_text(encoding="utf-8")

    # The stub is built from the English frontmatter; a drift here would make the
    # host agent stop (or start) triggering on the skill.
    assert skill_assembly.split_frontmatter(ru)[0] == skill_assembly.split_frontmatter(en)[0]
    # Same shape, and every 🔒 stays on the same heading: a translation must not
    # drop a rule the user cannot override.
    assert _headings(ru) == _headings(en)


@pytest.mark.parametrize("skill", SKILLS)
def test_translation_keeps_every_code_token(skill):
    """Tool names, fields and values live in backticks and must survive verbatim."""
    en = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    ru = (SKILLS_DIR / skill / "SKILL.ru-RU.md").read_text(encoding="utf-8")
    ticks = lambda t: sorted(set(re.findall(r"`([^`\n]+)`", t)))
    missing = [t for t in ticks(en) if t not in ru]
    assert not missing, f"{skill}: code tokens lost in translation: {missing}"


def test_read_skill_serves_the_translation_when_configured(tmp_vault, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "ru-RU")

    out = api.read_skill("loci-save")

    ru_body = skill_assembly.split_frontmatter(
        (SKILLS_DIR / "loci-save" / "SKILL.ru-RU.md").read_text(encoding="utf-8")
    )[1].strip()
    assert ru_body in out
    assert "Следуйте этому документу" in out
    assert skill_assembly.PROTECTED in out


def test_read_skill_is_english_by_default(tmp_vault):
    out = api.read_skill("loci-save")

    assert "Follow this document for the whole interaction" in out
    assert "Следуйте" not in out


def test_the_users_additions_are_still_appended_in_russian(tmp_vault, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "ru-RU")
    api.write_skill("Always ask twice.", "loci-save")

    out = api.read_skill("loci-save")

    assert out.index("Always ask twice.") > out.index(f"# {skill_assembly.OVERLAY_HEADING}")


def test_a_skill_without_a_translation_is_served_in_english(tmp_vault, monkeypatch):
    """No SKILL.<lang>.md must not fail, and must not get a Russian preamble over English text."""
    monkeypatch.setenv(ENV_VAR, "ru-RU")
    monkeypatch.setattr(skill_assembly, "SKILLS_DIR", tmp_vault / "skills-pkg")
    pkg = tmp_vault / "skills-pkg" / "loci-save"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("---\nname: loci-save\n---\n# english only 🔒\n")

    out = skill_assembly.assemble("loci-save", tmp_vault, "ru-RU")

    assert "english only" in out
    assert "Следуйте" not in out
    assert "Follow this document" in out

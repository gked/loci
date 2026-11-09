"""
The language Loci answers in: `language` in config.yml, or LOCI_LANGUAGE.

Two things follow from it. `read_skill` serves the Russian procedure
(`skills/<name>/SKILL.ru-RU.md`) when one ships, and `/api/health` reports it so
the web UI opens in that language until the user picks one in the rail.

Everything the model or a tool matches on stays English in every language:
tool names, type and relation names, frontmatter fields, and the SKILL.md
frontmatter the host agent triggers on. A language only changes prose.
"""

from __future__ import annotations

import os

import yaml

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ru-RU")
ENV_VAR = "LOCI_LANGUAGE"


# Mirrored by normalizeLanguage() in app/src/lib/i18n.js. Both are checked
# against tests/fixtures/language-normalize.json; change them together.
def normalize(value) -> str | None:
    """"ru", "ru_RU", "ru-ru" -> "ru-RU"; "en-US" -> "en"; anything else None."""
    if not isinstance(value, str):
        return None
    v = value.strip().replace("_", "-").lower()
    if v == "en" or v.startswith("en-"):
        return "en"
    if v in ("ru", "ru-ru"):
        return "ru-RU"
    return None


def _from_config_file() -> str | None:
    # Read the file directly: load_config() short-circuits to just the vault
    # root when LOCI_VAULT_ROOT is set, which would hide this key.
    # Imported here: vault_init imports skill_assembly, which imports this module.
    from loci.tools.vault_init import config_path

    try:
        path = config_path()
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None
    return normalize(data.get("language")) if isinstance(data, dict) else None


def get_language() -> str:
    """The configured language: env var, then config.yml, then English.

    An unrecognised value falls through to the next source rather than
    raising: a typo in a config file must not take the vault offline.
    """
    return normalize(os.environ.get(ENV_VAR)) or _from_config_file() or DEFAULT_LANGUAGE

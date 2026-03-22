"""
api.py
Loci vault API — clean interface for saving, reading, and listing vault items.

Used by:
  loci_mcp/server.py  — Claude Desktop (MCP tools)
  tools/         — CLI entry points

Internal implementation lives in tools/. This module is the public facade.
"""

import contextlib
import io
import sys
from pathlib import Path

# Add tools/ to path so we can import the implementation modules
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from uid_generator import generate_uid as _generate_uid
from vault_init import load_config
from write_file import (
    write_item as _write_item,
    check_duplicate as _check_duplicate,
    TYPE_FOLDERS,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vault_root() -> Path:
    config = load_config()
    if not config:
        raise RuntimeError("Loci is not configured. Run: python tools/vault_init.py")
    return Path(config["vault_root"]).expanduser()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_uid() -> str:
    """Generate a random 8-character hex UID."""
    return _generate_uid()


def save(
    type: str,
    title: str,
    body: str,
    tags: list = None,
    domains: list = None,
    summary: str = None,
    author: str = "self",
    relations: list = None,
    references: list = None,
    extra_fields: dict = None,
    date: str = None,
) -> dict:
    """
    Write a new item to the vault. Returns {uid, path, type, title}.

    Duplicate checking is not performed here — call check_duplicate first
    if needed and confirm with the user before calling save.
    """
    # Redirect stdout to prevent write_item's print() calls from corrupting
    # the MCP stdio protocol (or cluttering non-interactive use)
    with contextlib.redirect_stdout(io.StringIO()):
        return _write_item(
            type=type,
            title=title,
            body=body,
            tags=tags,
            domains=domains,
            summary=summary,
            author=author,
            relations=relations,
            references=references,
            extra_fields=extra_fields,
            date=date,
            skip_duplicate_check=True,
        )


def check_duplicate(type: str, title: str, url: str = None) -> dict:
    """
    Check whether a similar vault item already exists.
    Returns {"duplicate": False} or {"duplicate": True, "path": str, "name": str}.
    """
    folder = TYPE_FOLDERS.get(type)
    if not folder:
        raise ValueError(f"Unknown type: {type!r}. Must be one of: {list(TYPE_FOLDERS.keys())}")
    dup = _check_duplicate(_vault_root(), folder, title, url)
    if dup:
        return {"duplicate": True, "path": str(dup), "name": dup.name}
    return {"duplicate": False}


def get(path: str) -> str:
    """
    Read a vault file. Accepts an absolute path or a path relative to vault_root.
    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.is_absolute():
        p = _vault_root() / path
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")
    return p.read_text(encoding="utf-8")


def list_items(type: str = None) -> dict:
    """
    List items in a vault type folder (or all folders).
    Returns {type_name: [filename, ...], ...}.
    """
    vault_root = _vault_root()
    folders = {type: TYPE_FOLDERS[type]} if type and type in TYPE_FOLDERS else TYPE_FOLDERS
    return {
        t: sorted(f.name for f in (vault_root / folder).glob("*.md"))
        if (vault_root / folder).exists() else []
        for t, folder in folders.items()
    }


def read_meta(file: str) -> str:
    """
    Read a vault meta file.
    file: type-dictionary | tag-dictionary | foreign-definitions | config
    """
    vault_root = _vault_root()
    file_map = {
        "type-dictionary":    vault_root / "meta" / "type-dictionary.md",
        "tag-dictionary":     vault_root / "meta" / "tag-dictionary.md",
        "foreign-definitions": vault_root / "meta" / "foreign-definitions.md",
        "config":             vault_root / "meta" / "config.yml",
    }
    p = file_map.get(file)
    if not p:
        raise ValueError(f"Unknown meta file: {file!r}")
    if not p.exists():
        raise FileNotFoundError(f"Meta file not found: {p}")
    return p.read_text(encoding="utf-8")


def fetch_url_metadata(url: str) -> dict:
    """
    Lightly fetch a URL and extract title, site name, and description.
    Used for bookmark saves — does not return full page content.
    Returns {url, title, site_name, description} or adds an "error" key on failure.
    """
    import httpx
    from html.parser import HTMLParser

    class _MetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = None
            self.site_name = None
            self.description = None
            self._in_title = False

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "title":
                self._in_title = True
            elif tag == "meta":
                name = attrs.get("name", "").lower()
                prop = attrs.get("property", "").lower()
                content = attrs.get("content", "")
                if prop == "og:title" and not self.title:
                    self.title = content
                elif prop == "og:site_name":
                    self.site_name = content
                elif prop == "og:description" and not self.description:
                    self.description = content
                elif name == "description" and not self.description:
                    self.description = content

        def handle_data(self, data):
            if self._in_title and not self.title:
                self.title = data.strip()

        def handle_endtag(self, tag):
            if tag == "title":
                self._in_title = False

    try:
        response = httpx.get(url, follow_redirects=True, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; Loci/1.0)"})
        response.raise_for_status()
        parser = _MetaParser()
        parser.feed(response.text)
        return {
            "url": url,
            "title": parser.title or url,
            "site_name": parser.site_name,
            "description": parser.description,
        }
    except Exception as e:
        return {"url": url, "title": url, "site_name": None, "description": None, "error": str(e)}


def read_skill() -> str:
    """Read the current Loci skill instructions (skill/SKILL.md)."""
    p = Path(__file__).parent / "loci-skill" / "loci-save" / "SKILL.md"
    if not p.exists():
        raise FileNotFoundError(f"Skill file not found: {p}")
    return p.read_text(encoding="utf-8")


def write_skill(content: str) -> str:
    """
    Overwrite the Loci skill instructions (skill/SKILL.md). Returns the path written.
    Since ~/.claude/skills/loci-save/ is a symlink to skill/, Claude Code picks
    up the update automatically. Claude Desktop users will need to re-paste.
    """
    p = Path(__file__).parent / "loci-skill" / "loci-save" / "SKILL.md"
    if not p.exists():
        raise FileNotFoundError(f"Skill file not found: {p}")
    p.write_text(content, encoding="utf-8")
    return str(p)


def write_meta(file: str, content: str) -> str:
    """
    Overwrite a vault meta file. Returns the path written.
    file: tag-dictionary | foreign-definitions
    (type-dictionary and config are read-only via this API)
    """
    vault_root = _vault_root()
    file_map = {
        "tag-dictionary":      vault_root / "meta" / "tag-dictionary.md",
        "foreign-definitions": vault_root / "meta" / "foreign-definitions.md",
    }
    p = file_map.get(file)
    if not p:
        raise ValueError(
            f"Unknown or read-only meta file: {file!r}. "
            f"Writable files: tag-dictionary, foreign-definitions"
        )
    p.write_text(content, encoding="utf-8")
    return str(p)

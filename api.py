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

import yaml

# Add tools/ to path so we can import the implementation modules
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from uid_generator import generate_uid as _generate_uid
from vault_init import load_config
from write_file import (
    write_item as _write_item,
    patch_item as _patch_item,
    check_duplicate as _check_duplicate,
)
from type_registry import get_registry
from relation_registry import get_relation_registry
import nx_graph as graph
from vault_linter import lint_vault as _lint_vault
import asset_registry as ar


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vault_root() -> Path:
    config = load_config()
    if not config:
        raise RuntimeError("Loci is not configured. Run: python tools/vault_init.py")
    return Path(config["vault_root"]).expanduser()


def _loci_root() -> Path:
    return _vault_root().parent


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
) -> dict:
    """
    Write a new item to the vault. Returns {uid, path, type, title}.

    Duplicate checking is not performed here — call check_duplicate first
    if needed and confirm with the user before calling save.
    """
    # Redirect stdout to prevent write_item's print() calls from corrupting
    # the MCP stdio protocol (or cluttering non-interactive use)
    with contextlib.redirect_stdout(io.StringIO()):
        result = _write_item(
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
            skip_duplicate_check=True,
        )
    if result and "uid" in result:
        graph.index_node(
            result["uid"],
            type=type,
            title=title,
            tags=tags or [],
            domains=domains or [],
            summary=summary or "",
            path=result["path"],
        )
        graph.index_edges(result["uid"], relations or [])
    return result


def delete(path: str) -> dict:
    """
    Delete a vault item. Accepts an absolute path or a path relative to vault_root.
    Returns {deleted: True, path: str} or raises FileNotFoundError.
    """
    p = Path(path)
    if not p.is_absolute():
        p = _vault_root() / path
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")
    # Read uid before deleting so we can drop the node from the graph
    uid = None
    raw = p.read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            uid = fm.get("uid")
    p.unlink()
    if uid:
        graph.drop_node(uid)
    return {"deleted": True, "path": str(p)}


def patch(path: str, updates: dict, body: str = None) -> dict:
    """
    Patch frontmatter fields in an existing vault item.
    `updates` is merged into the existing frontmatter; `updated_at` is always bumped.
    If `body` is provided, it replaces the existing body.
    Accepts an absolute path or a path relative to vault_root.
    Returns {uid, path, type, title}.
    """
    p = Path(path)
    if not p.is_absolute():
        p = _vault_root() / path
    result = _patch_item(str(p), updates, body)
    if result.get("uid"):
        graph.index_node(
            result["uid"],
            type=result.get("type", ""),
            title=result.get("title", ""),
            tags=result.get("tags", []),
            domains=result.get("domains", []),
            summary=result.get("summary", ""),
            path=str(p),
        )
        graph.index_edges(result["uid"], result.get("relations", []))
    return result


def check_duplicate(type: str, title: str, url: str = None) -> dict:
    """
    Check whether a similar vault item already exists.
    Returns {"duplicate": False} or {"duplicate": True, "path": str, "name": str}.
    """
    registry = get_registry(_vault_root())
    if type not in registry.type_names():
        raise ValueError(
            f"Unknown type: {type!r}. Must be one of: {sorted(registry.type_names())}"
        )
    dup = _check_duplicate(_vault_root(), title, url)
    if dup:
        return {"duplicate": True, "path": str(dup), "name": dup.name}
    return {"duplicate": False}


def get(path: str) -> str:
    """
    Read a vault file. Accepts an absolute path or a path relative to vault_root.
    Raises FileNotFoundError if the file does not exist.
    When the node has has_asset: true, asset content is appended inline (text files
    under the size threshold) or as a path reference (binary/large files).
    """
    p = Path(path)
    if not p.is_absolute():
        p = _vault_root() / path
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")

    text = p.read_text(encoding="utf-8")

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            uid = fm.get("uid")
            if uid and fm.get("has_asset"):
                try:
                    result = ar.resolve(_loci_root(), uid)
                    size = result["size_bytes"]
                    mime = result["mime_type"]
                    apath = result["path"]
                    if size <= ar.SIZE_THRESHOLD_BYTES and mime.startswith("text/"):
                        content = Path(apath).read_text(encoding="utf-8", errors="replace")
                        text += (
                            f"\n\n---\nasset_path: {apath}\n"
                            f"asset_mime_type: {mime}\n"
                            f"asset_size_bytes: {size}\n---\n\n"
                            f"{content}"
                        )
                    else:
                        text += (
                            f"\n\nasset_path: {apath}\n"
                            f"asset_mime_type: {mime}\n"
                            f"asset_size_bytes: {size}"
                        )
                except FileNotFoundError as e:
                    text += f"\n\nasset_content: null\nasset_error: {e}"

    return text


def resolve_asset(uid: str, format: str = None) -> dict:
    """
    Resolve an asset UID to its file path and metadata.
    Returns {path, mime_type, format, size_bytes}.
    """
    return ar.resolve(_loci_root(), uid, format)


def find_unregistered_assets() -> list:
    """Return relative paths of files in assets/ not listed in manifest.txt."""
    return ar.find_unregistered(_loci_root())


def save_asset(
    content: bytes,
    format: str,
    mime_type: str,
    title: str,
    summary: str = None,
    tags: list = None,
    domains: list = None,
    relations: list = None,
) -> dict:
    """
    Save a new asset with its vault proxy node using the crash-safe write sequence.
    Returns {uid, asset_path, vault_path}.
    """
    from slug import filename as make_filename

    uid = _generate_uid()
    loci_root = _loci_root()
    vault_root = _vault_root()

    asset_rel_path = f"assets/{uid}.{format}"
    asset_final = loci_root / asset_rel_path
    asset_tmp = ar.assets_dir(loci_root) / f".{uid}.{format}.tmp"

    vault_fname = make_filename(title)
    vault_path = vault_root / vault_fname

    vault_node = {
        "title": title,
        "summary": summary,
        "tags": tags or [],
        "domains": domains or [],
        "relations": relations or [],
    }

    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.registry_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.pending_dir(loci_root).mkdir(parents=True, exist_ok=True)

    # Step 1: Write intent file
    intent_path = ar.write_intent(
        loci_root, uid, format, mime_type,
        str(asset_tmp), asset_rel_path, str(vault_path), vault_node,
    )

    # Steps 2+3: Stage to tmp, rename to final (atomic)
    asset_tmp.write_bytes(content)
    asset_tmp.rename(asset_final)

    # Step 4: Write registry entry
    ar.write_registry_entry(loci_root, uid, format, mime_type, asset_rel_path)

    # Step 5: Append to manifest
    ar.append_manifest(loci_root, asset_rel_path)

    # Step 6: Write vault proxy node
    with contextlib.redirect_stdout(io.StringIO()):
        result = _write_item(
            type="document",
            title=title,
            body=f"# {title}\n",
            tags=tags,
            domains=domains,
            summary=summary,
            relations=relations,
            extra_fields={"uid": uid, "has_asset": True, "status": "evergreen"},
            skip_duplicate_check=True,
        )
    graph.index_node(
        uid,
        type="document",
        title=title,
        tags=tags or [],
        domains=domains or [],
        summary=summary or "",
        path=result["path"],
    )
    graph.index_edges(uid, relations or [])

    # Step 7: Delete intent file
    intent_path.unlink()

    return {"uid": uid, "asset_path": str(asset_final), "vault_path": result["path"]}


def list_items(type: str = None) -> dict:
    """
    List items in the vault, optionally filtered by type.
    Reads frontmatter from each file to determine type.
    Returns {type_name: [filename, ...], ...}.
    """
    vault_root = _vault_root()
    result: dict = {}
    for path in sorted(vault_root.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1]) or {}
        node_type = fm.get("type")
        if not node_type:
            continue
        if type and node_type != type:
            continue
        result.setdefault(node_type, []).append(path.name)
    return result


def _append_yaml_entry(path: Path, list_key: str, entry: dict) -> None:
    """Append an entry to a YAML list file, preserving the comment header.
    Assumes all leading comment/blank lines form the header; inline comments are not preserved."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            header_end = i + 1
        else:
            break
    header = "".join(lines[:header_end])
    data = yaml.safe_load(text) or {list_key: []}
    entries = list(data.get(list_key) or [])
    entries.append(entry)
    dumped = yaml.dump(
        {list_key: entries},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    path.write_text(header + dumped, encoding="utf-8")


def define_type(
    name: str,
    extends: str,
    description: str,
    fields: list[dict] = None,
) -> dict:
    """
    Validate and append a new user-defined type to ontology-user.yaml.
    Returns {"defined": True, "name": str, "extends": str} on success,
    or {"defined": False, "errors": [...]} on validation failure.
    """
    from type_registry import reset_registry
    vault_root = _vault_root()
    result = get_registry(vault_root).validate_user_type(name, extends, fields)
    if not result["valid"]:
        return {"defined": False, "errors": result["errors"]}

    user_path = vault_root / "meta" / "ontology-user.yaml"
    if not user_path.exists():
        raise FileNotFoundError(f"User ontology not found: {user_path}")

    entry: dict = {"name": name, "extends": extends, "description": description}
    if fields:
        field_list = [
            {k: v for k, v in {
                "name": f["name"],
                "type": f.get("type", "string"),
                "values": f.get("values"),
            }.items() if v is not None}
            for f in fields
        ]
        if field_list:
            entry["fields"] = {"optional": field_list}

    _append_yaml_entry(user_path, "types", entry)
    reset_registry()
    return {"defined": True, "name": name, "extends": extends}


def define_relation(
    name: str,
    description: str,
    group: str = "",
    inverse_of: str = None,
) -> dict:
    """
    Validate and append a new user-defined relation to relation-dictionary-user.yaml.
    Returns {"defined": True, "name": str, "warnings": [...]} on success,
    or {"defined": False, "errors": [...], "warnings": [...]} on failure.
    """
    from relation_registry import reset_relation_registry
    vault_root = _vault_root()
    result = get_relation_registry(vault_root).validate_user_relation(
        name, group=group, description=description, inverse_of=inverse_of
    )
    if not result["valid"]:
        return {"defined": False, "errors": result["errors"], "warnings": result["warnings"]}

    user_path = vault_root / "meta" / "relation-dictionary-user.yaml"
    if not user_path.exists():
        raise FileNotFoundError(f"User relation dictionary not found: {user_path}")

    entry: dict = {"name": name, "description": description}
    if group:
        entry["group"] = group
    if inverse_of:
        entry["inverse_of"] = inverse_of

    _append_yaml_entry(user_path, "relations", entry)
    reset_relation_registry()
    return {"defined": True, "name": name, "warnings": result["warnings"]}


def _app_version() -> str:
    """Read the app version from pyproject.toml."""
    p = Path(__file__).parent / "pyproject.toml"
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=")[1].strip().strip('"')
    return "unknown"  # pragma: no cover


def read_meta(file: str) -> str:
    """
    Read a vault meta file.
    file: type-dictionary | tag-dictionary | field-dictionary | relation-dictionary |
          foreign-definitions | ontology | ontology-user | config
    """
    if file == "config":
        cfg = load_config() or {}
        return f"app_version: {_app_version()}\nvault_root: {cfg.get('vault_root', '')}\n"

    vault_root = _vault_root()
    file_map = {
        "type-dictionary":           vault_root / "meta" / "type-dictionary.md",
        "tag-dictionary":            vault_root / "meta" / "tag-dictionary.md",
        "field-dictionary":          vault_root / "meta" / "field-dictionary.md",
        "relation-dictionary":       vault_root / "meta" / "relation-dictionary.yaml",
        "relation-dictionary-user":  vault_root / "meta" / "relation-dictionary-user.yaml",
        "foreign-definitions":       vault_root / "meta" / "foreign-definitions.md",
        "ontology":                  vault_root / "meta" / "ontology.yaml",
        "ontology-user":             vault_root / "meta" / "ontology-user.yaml",
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


def validate_type(name: str, extends: str, fields: list[dict] = None) -> dict:
    """
    Validate a proposed user type definition without writing anything.
    Returns {"valid": bool, "errors": [...], "resolved_fields": {...}}.
    """
    return get_registry(_vault_root()).validate_user_type(name, extends, fields)


def lint_vault() -> dict:
    """
    Run the vault linter over all vault files.
    Returns {"errors": [...], "warnings": [...], "stats": {...}}.
    """
    return _lint_vault(_vault_root())


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
    file: tag-dictionary | foreign-definitions | ontology-user
    (type-dictionary, ontology, and config are read-only via this API)
    """
    vault_root = _vault_root()
    file_map = {
        "tag-dictionary":      vault_root / "meta" / "tag-dictionary.md",
        "foreign-definitions": vault_root / "meta" / "foreign-definitions.md",
        "ontology-user":       vault_root / "meta" / "ontology-user.yaml",
    }
    p = file_map.get(file)
    if not p:
        raise ValueError(
            f"Unknown or read-only meta file: {file!r}. "
            f"Writable files: tag-dictionary, foreign-definitions, ontology-user"
        )
    p.write_text(content, encoding="utf-8")
    return str(p)

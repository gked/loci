"""
directory_scanner.py
Scan an arbitrary directory and identify which files already have vault nodes
via a has_asset local location.
"""

import os
from pathlib import Path

from loci.tools.frontmatter import load_frontmatter

_IGNORED_NAMES = {".DS_Store", ".localized", "Thumbs.db", "desktop.ini"}


def _format_from_path(p: Path) -> str:
    return p.suffix.lstrip(".").lower() or "unknown"


# Ebook formats become asset nodes (subtype book); everything else is a
# document that happens to point at a file. The skill used to carry this table
# in prose and re-derive it per file; keeping it here makes the suggestion the
# same on every run.
_EBOOK_FORMATS = {"epub", "mobi", "azw", "azw3"}


def _suggest_type(fmt: str) -> tuple[str, str | None]:
    if fmt in _EBOOK_FORMATS:
        return "asset", "book"
    return "document", None


def _suggest_title(p: Path) -> str:
    """Humanize a filename: drop the extension, break on `_`/`-`, title-case."""
    words = p.stem.replace("_", " ").replace("-", " ").split()
    return " ".join(w if w.isupper() else w.capitalize() for w in words) or p.name


def _gather_files(directory: Path, recursive: bool) -> list[Path]:
    results = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                fp = Path(root) / name
                if not name.startswith(".") and name not in _IGNORED_NAMES:
                    results.append(fp)
    else:
        for p in sorted(directory.iterdir()):
            if p.is_file() and not p.name.startswith(".") and p.name not in _IGNORED_NAMES:
                results.append(p)
    return results


def _local_path_index(vault_root: Path) -> dict[str, str]:
    """
    Return a mapping of resolved absolute path → node UID for every
    has_asset local location found in the vault.
    """
    index: dict[str, str] = {}
    for vf in vault_root.glob("*.md"):
        try:
            fm, _ = load_frontmatter(vf.read_text(encoding="utf-8"))
            if fm is None:
                continue
            uid = fm.get("uid")
            has_asset = fm.get("has_asset")
            if not uid or not isinstance(has_asset, list):
                continue
            for variant in has_asset:
                if not isinstance(variant, dict):
                    continue
                for loc in variant.get("locations", []):
                    if not isinstance(loc, dict) or loc.get("scheme") != "local":
                        continue
                    raw = loc.get("path", "")
                    if not raw:
                        continue
                    p = Path(raw)
                    if not p.is_absolute():
                        p = vault_root.parent / p
                    index[str(p.resolve())] = uid
        except Exception:
            continue
    return index


def scan_directory(
    directory: str,
    vault_root: Path,
    recursive: bool = False,
) -> dict:
    """
    Scan a directory and split its files into those that already have a vault
    node (via has_asset scheme: local) and those that don't.

    Returns:
        {
            "directory": str,
            "recursive": bool,
            "total_files": int,
            "unregistered": [{"path": str, "filename": str, "format": str,
                               "suggested_type": str, "suggested_subtype": str | None,
                               "suggested_title": str}, ...],
            "registered":   [{"path": str, "filename": str, "format": str,
                               "node_uid": str}, ...],
        }

    The suggested_* fields are derived from the filename alone: ebooks become
    `asset` / `book`, anything else `document`; the title is the humanized
    filename. They are a starting point for the model, not a decision.
    """
    dir_path = Path(directory).expanduser().resolve()
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {dir_path}")

    files = _gather_files(dir_path, recursive)
    index = _local_path_index(vault_root)

    unregistered: list[dict] = []
    registered: list[dict] = []

    for fp in files:
        resolved = str(fp.resolve())
        entry = {
            "path": str(fp),
            "filename": fp.name,
            "format": _format_from_path(fp),
        }
        uid = index.get(resolved)
        if uid:
            registered.append({**entry, "node_uid": uid})
        else:
            suggested_type, suggested_subtype = _suggest_type(entry["format"])
            unregistered.append({
                **entry,
                "suggested_type": suggested_type,
                "suggested_subtype": suggested_subtype,
                "suggested_title": _suggest_title(fp),
            })

    return {
        "directory": str(dir_path),
        "recursive": recursive,
        "total_files": len(files),
        "unregistered": unregistered,
        "registered": registered,
    }

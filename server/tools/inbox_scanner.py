"""Scan loci-stage and classify files for inbox processing."""

import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from inbox_plan import DEFAULT_BUDGET_FILES, DEFAULT_BUDGET_CONTENT
from metadata_extractor import extract_metadata, MIME_TYPES


EBOOK_SUFFIXES = frozenset({".epub", ".mobi", ".azw", ".azw3", ".djvu"})


def scan_stage(stage_root: Path) -> dict:
    """
    Scan loci-stage/ and classify all files.

    Returns:
        {
            items: [...classified items...],
            unresolved: [...unresolved items...],
            summary: {
                total_files, total_content, total_unresolved,
                runs_estimated: {files, content}
            }
        }

    Budget defaults: DEFAULT_BUDGET_FILES per run, DEFAULT_BUDGET_CONTENT per run.
    """
    items: list[dict] = []
    unresolved: list[dict] = []
    extraction_warnings: list[dict] = []

    files_dir = stage_root / "files"

    # --- Scan loci-stage/files/ (recurses into subdirectories) ---
    if files_dir.exists() and files_dir.is_dir():
        for f in sorted(files_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.name.startswith("."):
                continue

            suffix = f.suffix.lower()
            meta = extract_metadata(f)
            rel_path = str(f.relative_to(stage_root))
            if err := meta.get("_extraction_error"):
                extraction_warnings.append({"path": rel_path, "error": err})
            fmt = meta.get("format", suffix.lstrip("."))
            mime = meta.get("mime_type", "application/octet-stream")
            title = meta.get("title", f.stem)
            author = meta.get("author")
            language = meta.get("language")

            base: dict = {
                "path": rel_path,
                "format": fmt,
                "mime_type": mime,
                "title": title,
            }
            if author:
                base["author"] = author
            if language:
                base["language"] = language

            if suffix in EBOOK_SUFFIXES:
                items.append({**base, "category": "file", "action": "ingest-asset", "type": "asset", "subtype": "book"})
            elif suffix == ".pdf":
                # Unresolved: ambiguous without title metadata
                entry = {"path": rel_path, "reason": "Ambiguous: book or academic paper?"}
                if not meta.get("title") or title == f.stem:
                    entry["reason"] = "Ambiguous: book or academic paper? No title metadata found."
                entry["options"] = [
                    {"action": "ingest-asset", "type": "asset", "subtype": "book"},
                    {"action": "save-content", "type": "article"},
                ]
                unresolved.append(entry)
            else:
                unresolved.append({
                    "path": rel_path,
                    "reason": f"Unknown file extension: {suffix!r}",
                    "options": [],
                })

    # --- Scan flat loci-stage/ root (skip subdirs and hidden files) ---
    for f in sorted(stage_root.iterdir()):
        if f.is_dir():
            continue  # skip all subdirectories
        if f.name.startswith("."):
            continue  # skip hidden files including .inbox-plan.yaml
        if f.name == ".inbox-plan.yaml":
            continue

        suffix = f.suffix.lower()
        meta = extract_metadata(f)
        rel_path = str(f.relative_to(stage_root))
        if err := meta.get("_extraction_error"):
            extraction_warnings.append({"path": rel_path, "error": err})
        fmt = meta.get("format", suffix.lstrip("."))
        mime = meta.get("mime_type", "application/octet-stream")
        title = meta.get("title", f.stem)
        author = meta.get("author")
        language = meta.get("language")

        base: dict = {
            "path": rel_path,
            "format": fmt,
            "mime_type": mime,
            "title": title,
        }
        if author:
            base["author"] = author
        if language:
            base["language"] = language

        if suffix in EBOOK_SUFFIXES:
            items.append({**base, "category": "file", "action": "ingest-asset", "type": "asset", "subtype": "book"})
        elif suffix in {".md", ".txt"}:
            items.append({**base, "category": "content", "action": "save-document", "type": "document"})
        elif suffix in {".html", ".htm", ".webarchive", ".mhtml"}:
            result = {**base, "category": "content", "action": "save-content", "type": "article"}
            result["note"] = "Confirm: bookmark or article?"
            items.append(result)
        elif suffix == ".pdf":
            unresolved.append({
                "path": rel_path,
                "reason": "Ambiguous without context: book, paper, or document?",
                "options": [
                    {"action": "ingest-asset", "type": "asset", "subtype": "book"},
                    {"action": "save-content", "type": "article"},
                    {"action": "save-document", "type": "document"},
                ],
            })
        else:
            unresolved.append({
                "path": rel_path,
                "reason": f"Unknown file extension: {suffix!r}",
                "options": [],
            })

    # Assign sequential IDs to items
    for i, item in enumerate(items, start=1):
        item["id"] = i
    # Unresolved items don't need ids (they're queued by path)

    total_files = sum(1 for it in items if it.get("category") == "file")
    total_content = sum(1 for it in items if it.get("category") == "content")
    total_unresolved = len(unresolved)

    runs_files = math.ceil(total_files / DEFAULT_BUDGET_FILES) if total_files else 0
    runs_content = math.ceil(total_content / DEFAULT_BUDGET_CONTENT) if total_content else 0

    return {
        "items": items,
        "unresolved": unresolved,
        "extraction_warnings": extraction_warnings,
        "summary": {
            "total_files": total_files,
            "total_content": total_content,
            "total_unresolved": total_unresolved,
            "runs_estimated": {
                "files": runs_files,
                "content": runs_content,
            },
        },
    }

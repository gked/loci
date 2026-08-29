"""Scan loci-stage and classify files for inbox processing."""

import math
from pathlib import Path

import sys

from loci.tools.inbox_plan import DEFAULT_BUDGET_FILES, DEFAULT_BUDGET_CONTENT
from loci.tools.metadata_extractor import extract_metadata, MIME_TYPES


EBOOK_SUFFIXES = frozenset({".epub", ".mobi", ".azw", ".azw3", ".djvu"})
ARTICLE_SUFFIXES = frozenset({".html", ".htm", ".webarchive", ".mhtml"})
DOCUMENT_SUFFIXES = frozenset({".md", ".txt", ".pdf"})
CONTENT_SUFFIXES = ARTICLE_SUFFIXES | DOCUMENT_SUFFIXES


def scan_stage(stage_root: Path) -> dict:
    """
    Scan loci-stage/ and classify all files.

    Returns:
        {
            items: [...classified items...],
            summary: {total_files, total_content, runs_estimated: {files, content}}
        }

    Budget defaults: DEFAULT_BUDGET_FILES per run, DEFAULT_BUDGET_CONTENT per run.
    """
    items: list[dict] = []
    extraction_warnings: list[dict] = []

    for f in sorted(stage_root.iterdir()):
        if f.is_dir():
            if not f.name.startswith("."):
                extraction_warnings.append({"path": f.name + "/", "error": "Subdirectory skipped — move files to loci-stage/ root"})
            continue
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
        elif suffix in ARTICLE_SUFFIXES:
            items.append({**base, "category": "content", "action": "save-content", "type": "article"})
        elif suffix in DOCUMENT_SUFFIXES:
            items.append({**base, "category": "content", "action": "save-document", "type": "document"})
        else:
            extraction_warnings.append({"path": rel_path, "error": f"Skipped: unrecognised extension {suffix!r}"})

    for i, item in enumerate(items, start=1):
        item["id"] = i

    total_files = sum(1 for it in items if it.get("category") == "file")
    total_content = sum(1 for it in items if it.get("category") == "content")

    runs_files = math.ceil(total_files / DEFAULT_BUDGET_FILES) if total_files else 0
    runs_content = math.ceil(total_content / DEFAULT_BUDGET_CONTENT) if total_content else 0

    return {
        "items": items,
        "extraction_warnings": extraction_warnings,
        "summary": {
            "total_files": total_files,
            "total_content": total_content,
            "runs_estimated": {
                "files": runs_files,
                "content": runs_content,
            },
        },
    }

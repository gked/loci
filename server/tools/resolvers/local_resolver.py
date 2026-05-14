"""
resolvers/local_resolver.py
Resolver for the 'local' scheme — files on the local filesystem.

location fields:
  path  (required) — path relative to loci root (e.g. "assets/<uid>.pdf")

enumerate scope fields:
  path  (required) — directory path relative to loci root
"""

import mimetypes
from pathlib import Path

from .base import Resolver


class LocalResolver(Resolver):
    capabilities = ["resolve", "enumerate"]

    def __init__(self, loci_root: Path):
        self.loci_root = loci_root

    def resolve(self, location: dict) -> dict:
        rel = location.get("path")
        if not rel:
            raise ValueError("LocalResolver: location missing required 'path' field")
        p = self.loci_root / rel
        if not p.exists():
            raise FileNotFoundError(f"Local file not found: {p}")
        mime_type, _ = mimetypes.guess_type(str(p))
        stat = p.stat()
        return {
            "path": str(p),
            "size_bytes": stat.st_size,
            "mime_type": mime_type or "application/octet-stream",
            "metadata": {"mtime": stat.st_mtime},
        }

    def enumerate(self, scope: dict) -> list:
        rel = scope.get("path")
        if not rel:
            raise ValueError("LocalResolver: scope missing required 'path' field")
        dir_path = self.loci_root / rel
        if not dir_path.exists():
            raise FileNotFoundError(f"Local directory not found: {dir_path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")
        items = []
        for f in sorted(dir_path.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                rel_path = f.relative_to(self.loci_root)
                items.append({
                    "scheme": "local",
                    "path": str(rel_path),
                    "title": f.stem,
                })
        return items

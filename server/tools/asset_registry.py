"""
asset_registry.py
Manages the Loci asset registry — binary/rich files stored outside vault/.

Folder structure (siblings under ~/Nextcloud/loci/):
  assets/                  ← binary/rich files (local storage)
  asset-registry/          ← one YAML file per asset
    manifest.txt           ← flat list of all registered asset paths (one per line)
    .pending/              ← intent files for crash recovery
"""

import json
import yaml
from datetime import datetime, timezone
from pathlib import Path


SIZE_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def registry_dir(loci_root: Path) -> Path:
    return loci_root / "asset-registry"


def assets_dir(loci_root: Path) -> Path:
    return loci_root / "assets"


def pending_dir(loci_root: Path) -> Path:
    return registry_dir(loci_root) / ".pending"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _infer_scheme(path: str) -> str:
    if path.startswith("s3://"):
        return "s3"
    if path.startswith("nas:"):
        return "nas"
    if path.startswith("http://") or path.startswith("https://"):
        return "http"
    return "asset-vault"


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

def resolve(loci_root: Path, uid: str, fmt: str = None) -> dict:
    """
    Resolve an asset UID to a local file path.
    Returns {path, mime_type, format, size_bytes}.
    Raises FileNotFoundError if registry entry is missing or all locations fail.
    Raises ValueError if the requested format is not in the registry.
    """
    reg_path = registry_dir(loci_root) / f"{uid}.yaml"
    if not reg_path.exists():
        raise FileNotFoundError(f"No registry entry for asset {uid}")

    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    files = reg.get("files", [])

    if fmt:
        entry = next((f for f in files if f["format"] == fmt), None)
        if entry is None:
            raise ValueError(f"No {fmt!r} format for asset {uid}")
    else:
        entry = next((f for f in files if f.get("primary")), files[0] if files else None)

    if entry is None:
        if reg.get("physical"):
            raise FileNotFoundError(
                f"Asset {uid} is a physical-only asset with no digital files"
            )
        raise FileNotFoundError(f"Registry entry for {uid} has no files")

    failed = []
    for loc in sorted(entry["locations"], key=lambda l: l.get("priority", 999)):
        if loc["scheme"] == "asset-vault":
            p = loci_root / loc["path"]
            if p.exists():
                return {
                    "path": str(p),
                    "mime_type": entry.get("mime_type", "application/octet-stream"),
                    "format": entry["format"],
                    "size_bytes": p.stat().st_size,
                }
            failed.append(loc["path"])

    raise FileNotFoundError(f"Asset {uid} not reachable. Tried: {failed}")


# ---------------------------------------------------------------------------
# Write sequence helpers
# ---------------------------------------------------------------------------

def write_registry_entry(
    loci_root: Path, uid: str, fmt: str, mime_type: str, asset_rel_path: str
) -> None:
    """Write asset-registry/<uid>.yaml."""
    rd = registry_dir(loci_root)
    rd.mkdir(parents=True, exist_ok=True)

    entry = {
        "uid": uid,
        "registered_at": _now(),
        "files": [
            {
                "format": fmt,
                "mime_type": mime_type,
                "primary": True,
                "locations": [
                    {
                        "scheme": "asset-vault",
                        "path": asset_rel_path,
                        "priority": 1,
                        "last_verified_at": _now(),
                    }
                ],
            }
        ],
    }

    reg_path = rd / f"{uid}.yaml"
    reg_path.write_text(
        yaml.dump(entry, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def write_physical_entry(loci_root: Path, uid: str, physical_instances: list[dict]) -> None:
    """
    Write asset-registry/<uid>.yaml for a physical-only asset (no digital file).

    physical_instances is a list of dicts, each with at minimum:
      format   str  — e.g. "paperback", "coin", "vehicle", "photo-album"
      location str  — where it is physically

    Optional keys per instance: condition, acquired_at, quantity, attributes, notes.
    """
    rd = registry_dir(loci_root)
    rd.mkdir(parents=True, exist_ok=True)

    entry = {
        "uid": uid,
        "registered_at": _now(),
        "files": [],
        "physical": physical_instances,
    }

    reg_path = rd / f"{uid}.yaml"
    reg_path.write_text(
        yaml.dump(entry, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def add_physical_instance(loci_root: Path, uid: str, instance: dict) -> None:
    """
    Append a physical instance to an existing asset-registry entry.
    Creates a minimal entry (no files) if none exists yet.

    instance must have at minimum: format (str) and location (str).
    """
    rd = registry_dir(loci_root)
    rd.mkdir(parents=True, exist_ok=True)
    reg_path = rd / f"{uid}.yaml"

    if reg_path.exists():
        entry = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    else:
        entry = {"uid": uid, "registered_at": _now(), "files": []}

    physical = entry.get("physical") or []
    physical.append(instance)
    entry["physical"] = physical

    reg_path.write_text(
        yaml.dump(entry, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def append_manifest(loci_root: Path, asset_rel_path: str) -> None:
    """
    Add a path to asset-registry/manifest.txt and update per-scheme counts.

    Format:
      # local: 2
      # s3: 1
      assets/87fb4c65.html
      assets/a1cab730.png
      s3://my-bucket/loci/abc123.pdf

    Rewrites the file on each call so counts stay accurate.
    """
    registry_dir(loci_root).mkdir(parents=True, exist_ok=True)
    manifest = registry_dir(loci_root) / "manifest.txt"

    # Read existing entries, skipping comment lines
    entries = []
    if manifest.exists():
        entries = [
            l for l in manifest.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]

    if asset_rel_path not in entries:
        entries.append(asset_rel_path)

    # Count by scheme
    counts: dict[str, int] = {}
    for entry in entries:
        s = _infer_scheme(entry)
        counts[s] = counts.get(s, 0) + 1

    header = [f"# {s}: {counts[s]}" for s in sorted(counts)]
    manifest.write_text("\n".join(header + [""] + entries) + "\n", encoding="utf-8")


def write_intent(
    loci_root: Path,
    uid: str,
    fmt: str,
    mime_type: str,
    asset_tmp_path: str,
    asset_rel_path: str,
    vault_path: str,
    vault_node: dict,
) -> Path:
    """Write .pending/<uid>.json intent file. Returns intent path."""
    pd = pending_dir(loci_root)
    pd.mkdir(parents=True, exist_ok=True)

    intent = {
        "uid": uid,
        "format": fmt,
        "mime_type": mime_type,
        "asset_tmp_path": asset_tmp_path,
        "asset_rel_path": asset_rel_path,
        "vault_path": vault_path,
        "vault_node": vault_node,
    }

    intent_path = pd / f"{uid}.json"
    intent_path.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    return intent_path


# ---------------------------------------------------------------------------
# Find unregistered
# ---------------------------------------------------------------------------

def find_unregistered(loci_root: Path) -> list:
    """Return relative paths of files in assets/ not listed in manifest.txt."""
    ad = assets_dir(loci_root)
    if not ad.exists():
        return []

    manifest = registry_dir(loci_root) / "manifest.txt"
    registered = (
        set(
            l for l in manifest.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        )
        if manifest.exists()
        else set()
    )

    return [
        f"assets/{f.name}"
        for f in sorted(ad.iterdir())
        if f.is_file()
        and not f.name.startswith(".")
        and f"assets/{f.name}" not in registered
    ]


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------

def recover_pending(loci_root: Path, vault_root: Path, write_vault_proxy_fn) -> list:
    """
    On startup: scan .pending/ and resume any interrupted write sequences.

    write_vault_proxy_fn(vault_root, uid, vault_node_fields) -> str
        Called to (re)write the vault proxy node; should return the vault file path.

    Returns list of UIDs that were recovered.
    """
    pd = pending_dir(loci_root)
    if not pd.exists():
        return []

    recovered = []
    for intent_file in pd.glob("*.json"):
        intent = json.loads(intent_file.read_text(encoding="utf-8"))
        uid = intent["uid"]
        fmt = intent["format"]
        mime_type = intent["mime_type"]
        asset_tmp = Path(intent["asset_tmp_path"])
        asset_rel = intent["asset_rel_path"]
        asset_final = loci_root / asset_rel
        reg_path = registry_dir(loci_root) / f"{uid}.yaml"
        manifest_path = registry_dir(loci_root) / "manifest.txt"
        vault_path = Path(intent["vault_path"])
        vault_node = intent["vault_node"]

        if not asset_tmp.exists() and not asset_final.exists():
            # Crash before any file was written — nothing to recover
            intent_file.unlink()
            continue

        # Step 3: rename tmp → final
        if asset_tmp.exists() and not asset_final.exists():
            asset_tmp.rename(asset_final)

        # Step 4: write registry entry
        if not reg_path.exists():
            write_registry_entry(loci_root, uid, fmt, mime_type, asset_rel)

        # Step 5: append to manifest
        if manifest_path.exists():
            registered = set(
                l for l in manifest_path.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")
            )
        else:
            registered = set()
        if asset_rel not in registered:
            append_manifest(loci_root, asset_rel)

        # Step 6: write vault proxy node
        if not vault_path.exists():
            write_vault_proxy_fn(vault_root, uid, vault_node)

        # Step 7: delete intent file
        intent_file.unlink()
        recovered.append(uid)

    return recovered

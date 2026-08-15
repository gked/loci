"""
vault_init.py
Initializes the Loci vault folder structure and config file.

Run this once on first setup, or to repair a missing vault structure.
Config is stored at ~/.config/loci/config.yml — see config_path().
"""

import contextlib
import io
import os
import shutil
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Where config lived before it moved out of the checkout. A uvx install has no
# checkout — the package is unpacked into an ephemeral uv cache — so a path
# relative to __file__ would be wiped on every update. Kept only to migrate off.
LEGACY_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yml"
REFERENCES_DIR = Path(__file__).parent.parent / "skills" / "references"

META_VERSION = 8

# Records META_VERSION inside the vault. Only env-var mode (Docker) relies on
# it; a config.yml install tracks the same number there.
VERSION_MARKER = ".meta-version"

VAULT_FOLDERS = [
    "meta",
]

# Reseeded on every META_VERSION bump.
META_FILES = [
    "type-dictionary.md",
    "tag-dictionary.md",
    "field-dictionary.md",
    "relation-dictionary.md",    # human-readable reference; kept alongside the machine-readable registry
    "relation-dictionary.yaml",
    "foreign-definitions.md",
    "ontology.yaml",
    "scheme-dictionary.yaml",
    "ontology-guide.md",         # the user's guide to the ontology; prose, not vocabulary
]

# Seeded once on first setup, never overwritten — user owns these.
USER_META_FILES = [
    "ontology-user.yaml",
    "relation-dictionary-user.yaml",
    "scheme-dictionary-user.yaml",
]


def config_path() -> Path:
    """
    Resolve the config file location.

    LOCI_CONFIG wins — that is how `make dev` points at a scratch config and how
    the tests stay off the real one. Otherwise the user-level file, under
    XDG_CONFIG_HOME when set so the XDG convention is honoured on Linux.

    Resolved per call rather than bound at import so the environment can change
    between them; callers must not cache the result.
    """
    override = os.environ.get("LOCI_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "loci" / "config.yml"


def migrate_legacy_config() -> Optional[str]:
    """
    Move a pre-existing <project_root>/config.yml to the user-level location.

    Runs at most once in effect: after the copy the destination exists, so every
    later call returns early. The legacy file is renamed rather than deleted —
    the values are recoverable, and leaving it in place would give the install
    two configs that silently drift.

    Skipped when LOCI_CONFIG is set: an explicit override means "use exactly
    this file", so migrating into it would be a surprise.
    """
    if os.environ.get("LOCI_CONFIG"):
        return None
    dest = config_path()
    if dest.exists() or not LEGACY_CONFIG_PATH.exists():
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_CONFIG_PATH, dest)

    retired = LEGACY_CONFIG_PATH.with_name(LEGACY_CONFIG_PATH.name + ".migrated")
    if retired.exists():
        # Somebody migrated before and put a config.yml back. Copying is done;
        # leave both files alone rather than clobbering the older backup.
        return f"Loci config was copied to {dest}. {LEGACY_CONFIG_PATH} is now unused."
    LEGACY_CONFIG_PATH.rename(retired)
    return (
        f"Loci config moved from {LEGACY_CONFIG_PATH} to {dest}. "
        f"The old file is kept as {retired.name} and is no longer read."
    )


def load_config() -> Optional[dict]:
    """Load existing config if present. LOCI_VAULT_ROOT env var takes precedence."""
    vault_root_env = os.environ.get("LOCI_VAULT_ROOT")
    if vault_root_env:
        return {"vault_root": vault_root_env}
    migrate_legacy_config()
    path = config_path()
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return None


def save_config(config: dict) -> None:
    """Save config to the user-level config file, creating its directory."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Config saved to {path}")


def create_vault_structure(vault_root: Path, include_siblings: bool = True) -> None:
    """Create vault folder structure, asset storage, and seed meta files.

    include_siblings=False skips the assets/ and loci-stage/ directories that
    normally sit next to the vault. In env-var mode the vault is a bind mount
    and its parent is the container root, so creating them there would write
    outside the mount, where the contents vanish on the next container start.
    """
    vault_root.mkdir(parents=True, exist_ok=True)

    for folder in VAULT_FOLDERS:
        folder_path = vault_root / folder
        folder_path.mkdir(exist_ok=True)
        print(f"  Created: {folder_path}")

    if include_siblings:
        # Asset storage lives alongside vault/, not inside it
        loci_root = vault_root.parent
        for folder in ["assets", "asset-registry/.pending"]:
            p = loci_root / folder
            p.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {p}")

        # Staging folder lives alongside vault/, not inside it
        stage_root = loci_root / "loci-stage"
        stage_root.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {stage_root}")

    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        if not dest.exists():
            dest.write_text(src.read_text())
            print(f"  Seeded: {dest}")

    for filename in USER_META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        if not dest.exists():
            dest.write_text(src.read_text())
            print(f"  Seeded (user): {dest}")


def write_vault_meta_version(vault_root: Path, version: int) -> None:
    """Record the seeded meta version inside the vault."""
    marker = vault_root / "meta" / VERSION_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{version}\n")


def reseed_meta(vault_root: Path) -> None:
    """Force overwrite canonical meta files from loci-skill/references/.
    USER_META_FILES are never touched — the user owns those."""
    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        dest.write_text(src.read_text())
        print(f"  Re-seeded: {dest}")


def setup_interactive() -> dict:
    """Interactive first-run setup flow."""
    print("\nLoci is not configured yet. Let's set it up.\n")

    default_vault = Path(__file__).parent.parent / "knowledge-vault"
    vault_input = input(f"Where should the vault live? (default: {default_vault}): ").strip()
    vault_root = Path(vault_input) if vault_input else default_vault

    remote = input("rclone remote name for sync (e.g. nextcloud, dropbox — leave blank to skip): ").strip()
    remote_path = ""
    if remote:
        remote_path = input("Path on the remote (default: loci): ").strip() or "loci"

    config = {
        "vault_root": str(vault_root),
        "sync_remote": remote or None,
        "sync_remote_path": remote_path or "loci",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "meta_version": META_VERSION,
    }

    return config


def read_vault_meta_version(vault_root: Path) -> Optional[int]:
    """Read the meta version marker stored inside the vault, if any."""
    marker = vault_root / "meta" / VERSION_MARKER
    if not marker.exists():
        return None
    try:
        return int(marker.read_text().strip())
    except ValueError:
        return None  # corrupt marker: treat as unversioned and reseed


def _canonical_meta_complete(vault_root: Path) -> bool:
    """True when every canonical meta file is already present in the vault."""
    return all((vault_root / "meta" / name).exists() for name in META_FILES)


def describe_vault_location(vault_root: Path) -> str:
    """
    Describe the vault path in terms the user can act on.

    Inside a container, vault_root is the mount point, which tells the user
    nothing about where their files actually live. /proc/self/mountinfo carries
    the host directory backing that mount, so report both when they differ.
    """
    host_path = _host_path_for_mount(vault_root)
    if host_path and host_path != str(vault_root):
        return f"{host_path} (mounted in the container at {vault_root})"
    return str(vault_root)


# mountinfo escapes these four characters in its path fields.
_MOUNTINFO_ESCAPES = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}


def _unescape_mountinfo(field: str) -> str:
    """Decode the octal escapes mountinfo applies to whitespace and backslashes.

    Without this a vault under `/Users/me/My Files/vault` reads back as
    `/Users/me/My\\040Files/vault`, and a mount point containing a space never
    matches the path we are looking for.
    """
    if "\\" not in field:
        return field
    out: list[str] = []
    i = 0
    while i < len(field):
        code = field[i + 1:i + 4]
        if field[i] == "\\" and code in _MOUNTINFO_ESCAPES:
            out.append(_MOUNTINFO_ESCAPES[code])
            i += 4
        else:
            out.append(field[i])
            i += 1
    return "".join(out)


def _host_path_for_mount(vault_root: Path, mountinfo: Optional[Path] = None) -> Optional[str]:
    """Resolve the host directory backing a bind mount, if discoverable.

    Best-effort only: field 4 is the root *within the source filesystem*, so on
    a host where the vault's parent is its own filesystem (a separate /home,
    say) the path comes back without that prefix. Callers use it to point the
    user in the right direction, never to open a file.
    """
    mountinfo = mountinfo or Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return None  # not Linux, or not containerized
    try:
        lines = mountinfo.read_text().splitlines()
    except OSError:
        return None

    target = str(vault_root)
    result = None
    for line in lines:
        # <id> <parent> <maj:min> <root> <mount point> ...
        fields = line.split()
        if len(fields) >= 5 and _unescape_mountinfo(fields[4]) == target:
            source = _unescape_mountinfo(fields[3])
            # Named volumes resolve under Docker's own storage — technically
            # correct but not somewhere the user should go looking.
            result = None if source.startswith("/var/lib/docker") else source
            # Keep scanning: a later line for the same mount point overmounts
            # the earlier one, and the last entry is what the path resolves to.
    return result


def ensure_env_vault(vault_root: Path) -> str | None:
    """
    Seed and upgrade a vault addressed by LOCI_VAULT_ROOT (Docker).

    There is no config.yml to record meta_version against — the image's copy is
    ephemeral — so the version marker lives in the vault itself, which is the
    bind-mounted volume that survives container restarts.

    Returns a notice string when something was seeded or upgraded, else None.
    """
    if not vault_root.is_dir():
        # Creating it would succeed — and that is the problem. In Docker the
        # missing directory means the volume was never mounted, so the seeded
        # files would land in the container's writable layer and be discarded
        # on the next `docker run`, having reported success.
        notice = (
            f"Vault path {vault_root} does not exist, so nothing was seeded. "
            f"In Docker this usually means the volume was not mounted — re-run "
            f"with -v /host/path/vault:{vault_root}. Otherwise create the "
            f"directory and restart. Loci is running on its built-in meta files "
            f"in the meantime; anything saved will not be kept."
        )
        print(notice, file=sys.stderr)
        return notice

    # This runs at server import, before a transport is chosen. Under stdio,
    # stdout is the JSON-RPC channel, so the seeding helpers' print() calls
    # would corrupt it — same reason api.py redirects around write_item.
    with contextlib.redirect_stdout(io.StringIO()):
        if not (vault_root / "meta").is_dir():
            create_vault_structure(vault_root, include_siblings=False)
            write_vault_meta_version(vault_root, META_VERSION)
            notice = (
                f"Vault at {describe_vault_location(vault_root)} was empty and "
                f"has been seeded with meta files at v{META_VERSION}."
            )
        else:
            current = read_vault_meta_version(vault_root)
            if current is not None and current >= META_VERSION:
                return None
            if current is None and _canonical_meta_complete(vault_root):
                # A vault set up by the local wizard has a full meta/ but no
                # marker — only this path writes one. Reseeding it would
                # overwrite tag-dictionary.md and foreign-definitions.md, which
                # are the user's to edit. A complete meta/ is evidence enough
                # that the vault is current: adopt it and record the version.
                # create_vault_structure only writes files that are missing, so
                # it fills USER_META_FILES gaps without touching anything else.
                create_vault_structure(vault_root, include_siblings=False)
                write_vault_meta_version(vault_root, META_VERSION)
                return None
            # Fills in USER_META_FILES too: reseed_meta only rewrites the
            # canonical set, and a vault seeded before this path existed has
            # neither.
            create_vault_structure(vault_root, include_siblings=False)
            reseed_meta(vault_root)
            write_vault_meta_version(vault_root, META_VERSION)
            from_version = f"v{current}" if current is not None else "unversioned"
            notice = (
                f"Vault meta files at {describe_vault_location(vault_root)} were "
                f"automatically updated from {from_version} to v{META_VERSION}. "
                f"No action needed."
            )

    # stderr, not stdout: visible in `docker logs` without waiting for the
    # _notice channel, which only reaches the user on the next list_vault.
    print(notice, file=sys.stderr)
    return notice


def check_meta_version() -> str | None:
    """
    Auto-reseed meta files at server startup if vault meta_version is older
    than META_VERSION. Returns a notice string if reseeding occurred so the
    caller can surface it to the user; returns None otherwise.
    """
    # Both branches below print while they work, and this runs at server import
    # where stdout is the stdio transport's JSON-RPC channel. Swallow it here so
    # the guard covers the config.yml path too, not just the Docker one.
    with contextlib.redirect_stdout(io.StringIO()):
        return _check_meta_version()


def _check_meta_version() -> str | None:
    vault_root_env = os.environ.get("LOCI_VAULT_ROOT")
    if vault_root_env:
        return ensure_env_vault(Path(vault_root_env))
    # The migration renames a file the user may still be pointing tools at
    # (sync.sh, their own scripts), so its notice rides out with whatever else
    # startup has to say rather than being dropped.
    migration_notice = migrate_legacy_config()
    path = config_path()
    if not path.exists():
        return migration_notice
    with open(path) as f:
        config = yaml.safe_load(f) or {}
    configured_root = config.get("vault_root")
    if not configured_root:
        return migration_notice
    vault_root = Path(configured_root)
    vault_meta_version = config.get("meta_version")
    if vault_meta_version is None or vault_meta_version < META_VERSION:
        reseed_meta(vault_root)
        config["meta_version"] = META_VERSION
        save_config(config)
        write_vault_meta_version(vault_root, META_VERSION)
        from_version = f"v{vault_meta_version}" if vault_meta_version is not None else "unversioned"
        return "\n".join(filter(None, [
            migration_notice,
            f"Vault meta files were automatically updated from {from_version} "
            f"to v{META_VERSION}. No action needed.",
        ]))
    # Config mode tracks the version in config.yml, but the vault itself may
    # later be addressed by LOCI_VAULT_ROOT (the same files, run under Docker).
    # Keep the in-vault marker in step so that path doesn't read the vault as
    # unversioned and reseed over the user's dictionaries.
    if read_vault_meta_version(vault_root) != META_VERSION and (vault_root / "meta").is_dir():
        write_vault_meta_version(vault_root, META_VERSION)
    return migration_notice


def init(force: bool = False) -> dict:
    """
    Initialize Loci. Returns the active config.

    Args:
        force: If True, re-seed all meta files from references/ and bump
               meta_version in config. Does not re-run interactive setup.
    """
    existing = load_config()

    if existing and force:
        vault_root = Path(existing["vault_root"])
        print(f"Re-seeding meta files at {vault_root / 'meta'}...")
        reseed_meta(vault_root)
        existing["meta_version"] = META_VERSION
        save_config(existing)
        print("Done.")
        return existing

    if existing and not force:
        print(f"Loci already configured. Vault root: {existing['vault_root']}")
        vault_root = Path(existing["vault_root"])
        print("Ensuring vault structure is complete...")
        create_vault_structure(vault_root)
        print("Done.")
        return existing

    config = setup_interactive()
    save_config(config)

    vault_root = Path(config["vault_root"])
    print(f"\nCreating vault structure at {vault_root}...")
    create_vault_structure(vault_root)

    print(f"\nLoci is ready. Vault at: {vault_root}\n")
    return config


if __name__ == "__main__":  # pragma: no cover
    force = "--force" in sys.argv
    init(force=force)

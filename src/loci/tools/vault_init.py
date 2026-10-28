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

from loci import skill_assembly


# Where config lived before it moved out of the checkout. A uvx install has no
# checkout — the package is unpacked into an ephemeral uv cache — so a path
# relative to __file__ would be wiped on every update. Kept only to migrate off.
#
# Four parents, because this module sits at src/loci/tools/: anything shallower
# aims the migration at src/config.yml, where no install ever wrote one, and
# every upgrading user silently lands back in the setup wizard.
LEGACY_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yml"
REFERENCES_DIR = Path(__file__).parent.parent / "skills" / "references"

META_VERSION = 16

# Records META_VERSION inside the vault. Only env-var mode (LOCI_VAULT_ROOT)
# relies on it; a config.yml install tracks the same number there.
VERSION_MARKER = ".meta-version"

VAULT_FOLDERS = [
    "meta",
    "skills",
]

# Every directory Loci seeds into the vault holds Loci's own files, never
# nodes: meta/ the registries, skills/ the user's skill overlays. Nodes live
# in type directories created on demand, so anything seeded here is something
# the vault walkers must skip — an overlay is free-form prose the user wrote,
# and one that happens to open with a `---` line would otherwise read as a
# node and be offered back as a duplicate. Derived from VAULT_FOLDERS so a
# folder added there is excluded by default rather than by remembering to.
NON_NODE_DIRS = frozenset(VAULT_FOLDERS)

# Reseeded on every META_VERSION bump. Nothing here is writable at runtime:
# api.write_meta() refuses every one of them, so overwriting can only ever
# replace packaged content with newer packaged content.
META_FILES = [
    "type-dictionary.md",
    "type-decision.md",
    "field-dictionary.md",
    "relation-dictionary.md",    # human-readable reference; kept alongside the machine-readable registry
    "relation-dictionary.yaml",
    "ontology.yaml",
    "scheme-dictionary.yaml",
    "ontology-guide.md",         # the user's guide to the ontology; prose, not vocabulary
    "has-asset-guide.md",        # loci-save reads this on demand instead of carrying it inline
    "update-workflow.md",        # ditto — the update / archive / delete procedure
]

# Seeded once into meta/ on first setup, never overwritten — user owns these.
#
# tag-dictionary.md and foreign-definitions.md sit here rather than in
# META_FILES because they are written at runtime: api.write_meta() accepts both
# by name, and loci-save appends a schema to foreign-definitions.md the first
# time it meets each external source. A vault that has been in use for a while
# holds a tag vocabulary and a set of source schemas that exist nowhere else,
# so a reseed would destroy work with no way back. That is also what README's
# "the files you own ... are never overwritten" promises.
#
# Everything here belongs to the *substrate*: it describes what the vault holds
# — which types and relations exist, what the tags and foreign terms mean. The
# three `-user` files extend a packaged registry and are merged with it by a
# loader, so they stay beside the file they extend. What they cannot do is
# override it: type_registry._load_user() skips any user type that omits
# `extends`, collides with a canonical name, or redefines an inherited field.
USER_META_FILES = [
    "ontology-user.yaml",
    "relation-dictionary-user.yaml",
    "scheme-dictionary-user.yaml",
    "tag-dictionary.md",
    "foreign-definitions.md",
]

# Seeded once into skills/, never overwritten — the user's half of each
# packaged skill, appended to the procedure by read_skill and written by
# write_skill (see skill_assembly.py).
#
# These are *policy*, not substrate: they say how a procedure should behave, not
# what the vault contains, and unlike the registry extensions above they are
# meant to override the packaged half — that is the contract read_skill states,
# with 🔒 headings as the only exception. Different rules, so a different
# directory; they lived in meta/ under their seed name until META_VERSION 14,
# and migrate_skill_overlays() moves any that are still there.
USER_SKILL_OVERLAYS = [
    "loci-save",
    "loci-query",
    "loci-inbox",
    "loci-ingest-directory",
]


# Every "Loci is not configured" message in the package renders this. It names
# the MCP tool first: an installed wheel has no checkout, so `setup.py` is a
# dead end for the reader most likely to hit this — someone who ran
# `uv tool install` and typed `loci`. The skills carry the same instruction for
# the same reason (see "Do not substitute a setup command for it" in
# loci-save/SKILL.md).
#
# One constant rather than a literal per call site: the four sites were copies,
# and three of them still told the reader to run `tools/vault_init.py` — a path
# that exists in no install and, since the package move, in no checkout either.
HOW_TO_CONFIGURE = (
    'ask Claude to "point Loci at ~/vault" (the set_vault_root tool), '
    "or run `uv run setup.py` from a checkout"
)
NOT_CONFIGURED_MESSAGE = f"Loci is not configured — {HOW_TO_CONFIGURE}"


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


def create_vault_structure(vault_root: Path, include_siblings: bool = True) -> list[str]:
    """Create vault folder structure, asset storage, and seed meta files.

    include_siblings=False skips the assets/ and loci-stage/ directories that
    normally sit next to the vault. In env-var mode (LOCI_VAULT_ROOT) the
    operator owns the vault directory and its parent is not ours to populate.

    Returns the skill overlays moved out of meta/ by this call, for the upgrade
    paths to put in their notice. Everything this function prints is swallowed
    by a redirect_stdout at every call site — under stdio that stream is the
    JSON-RPC channel — so a return value is the only way the move reaches the
    user, and it is their own file that moved.
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

    # Before seeding: a pre-v14 vault has the user's rules under meta/, and
    # seeding first would put a fresh empty stub in skills/ that the move then
    # had to refuse, stranding the real file.
    moved_overlays = migrate_skill_overlays(vault_root)

    for skill in USER_SKILL_OVERLAYS:
        dest = skill_assembly.overlay_path(vault_root, skill)
        src = REFERENCES_DIR / skill_assembly.seed_filename(skill)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text())
            print(f"  Seeded (user): {dest}")

    return moved_overlays


def overlay_move_notice(moved: list[str]) -> str | None:
    """One line naming the overlays the upgrade moved, or None if none did.

    The overlays are the one thing in the vault Loci did not write, and a user
    may be pointing an editor or a script at the old path, so the move says so
    for itself rather than hiding behind "meta files were updated".
    """
    if not moved:
        return None
    return (
        f"Your skill additions moved from vault/meta/ to "
        f"vault/{skill_assembly.OVERLAY_DIR}/: {', '.join(sorted(moved))}. "
        f"The contents are unchanged."
    )


def migrate_skill_overlays(vault_root: Path) -> list[str]:
    """Move pre-v14 skill overlays from meta/<skill>-user.md to skills/<skill>.md.

    Returns the skills moved. Idempotent: a vault with nothing left in meta/ is
    a no-op, so every seed and upgrade path can call it unconditionally.

    A destination that already exists is never overwritten — the user's rules
    are the one thing in the vault Loci did not write and cannot reconstruct.
    That leaves the old file in place rather than deleting it, which only
    happens if both were created by hand, and losing it silently would be worse
    than a stale copy the user can see.
    """
    moved = []
    for skill in USER_SKILL_OVERLAYS:
        old = skill_assembly.legacy_overlay_path(vault_root, skill)
        new = skill_assembly.overlay_path(vault_root, skill)
        if not old.is_file() or new.exists():
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
        moved.append(skill)
        print(f"  Moved: {old} -> {new}")
    return moved


def write_vault_meta_version(vault_root: Path, version: int) -> None:
    """Record the seeded meta version inside the vault."""
    marker = vault_root / "meta" / VERSION_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{version}\n")


def reseed_meta(vault_root: Path) -> None:
    """Force overwrite canonical meta files from references/.

    USER_META_FILES and USER_SKILL_OVERLAYS are never touched — the user owns
    those, and several of them (tag-dictionary.md, foreign-definitions.md, every
    skill overlay) accumulate content that exists nowhere but the vault. Call
    create_vault_structure() first if the vault may be missing files: this only
    rewrites what META_FILES lists, and the overlay move lives there too."""
    for filename in META_FILES:
        dest = vault_root / "meta" / filename
        src = REFERENCES_DIR / filename
        dest.write_text(src.read_text())
        print(f"  Re-seeded: {dest}")


def prompt_optional(text: str) -> str:
    """
    Ask for something that may be left blank.

    EOF means the same thing as an empty line here: skip it. That is what makes
    `echo /path/to/vault | loci-setup` work — the vault path is consumed, and
    the optional sync prompts that follow are simply skipped instead of dying on
    a bare EOFError after the user has already given the one required answer.
    """
    try:
        return input(text).strip()
    except EOFError:
        print()
        return ""


def prompt_vault_root() -> Path:
    """
    Ask for the vault location. There is deliberately no default.

    Any default we could pick would be wrong: a path next to this file lands in
    the uv cache that uvx wipes on every update, and a guess like ~/loci would
    quietly put the vault somewhere the user never syncs. So keep asking until
    an absolute path is given. `~` is expanded, since a shell is not doing it.

    Every rejection re-prompts. This is the one answer setup cannot proceed
    without, so a typo must never end the run — including a typo in the tilde
    (`~typo/vault`), which raises rather than returning something unusable, and
    a path that cannot be created, which would otherwise only surface after the
    config was written and leave no way back to this prompt.
    """
    while True:
        try:
            raw = input("Where should the vault live? (absolute path, required): ").strip()
        except EOFError:
            raise SystemExit(
                "\nNo vault path given. Run setup on a terminal, or set "
                "vault_root in " + str(config_path()) + " by hand."
            )
        if not raw:
            print("  A vault path is required — there is no default.")
            continue
        try:
            candidate = Path(raw).expanduser()
        except (RuntimeError, KeyError):
            # No such user, or no home directory to expand ~ against.
            print(f"  Could not work out what {raw} expands to. Start from / or ~/.")
            continue
        if not candidate.is_absolute():
            print(f"  {candidate} is not an absolute path. Start from / or ~.")
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"  Cannot create {candidate}: {exc}")
            continue
        return candidate


def setup_interactive() -> dict:
    """Interactive first-run setup flow."""
    print("\nLoci is not configured yet. Let's set it up.\n")

    vault_root = prompt_vault_root()

    remote = prompt_optional(
        "rclone remote name for sync (e.g. nextcloud, dropbox — leave blank to skip): "
    )
    remote_path = ""
    if remote:
        remote_path = prompt_optional("Path on the remote (default: loci): ") or "loci"

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


def _vault_content_missing(vault_root: Path) -> bool:
    """
    True when an existing vault directory holds nothing at all.

    Distinct from a missing directory: a sync folder that has remounted as a
    placeholder is present and empty, and writing into it looks like success.
    """
    if (vault_root / "meta").is_dir():
        return False
    try:
        return not any(vault_root.iterdir())
    except OSError:
        return True


def _meta_needs_upgrade(vault_root: Path) -> bool:
    """
    True when an existing vault's canonical meta files are behind the packaged
    ones and have to be overwritten.

    Must be called *before* create_vault_structure(): that fills in whatever is
    missing, which makes an out-of-date vault look complete.
    """
    if not (vault_root / "meta").is_dir():
        return False  # nothing seeded yet — seeding writes the current files
    current = read_vault_meta_version(vault_root)
    if current is not None:
        return current < META_VERSION
    # No marker at all. A complete canonical set is a vault the local wizard
    # set up before markers existed: adopt it rather than read the missing
    # marker as staleness. Same reasoning as ensure_env_vault().
    return not _canonical_meta_complete(vault_root)


def ensure_env_vault(vault_root: Path) -> str | None:
    """
    Seed and upgrade a vault addressed by LOCI_VAULT_ROOT.

    There is no config.yml to record meta_version against, so the version
    marker lives in the vault itself.

    Returns a notice string when something was seeded or upgraded, else None.
    """
    if not vault_root.is_dir():
        # LOCI_VAULT_ROOT names a directory the operator is responsible for.
        # Creating it would hide a typo in the path behind a fresh, empty vault.
        notice = (
            f"Vault path {vault_root} does not exist, so nothing was seeded. "
            f"Check the path in LOCI_VAULT_ROOT. If it is correct, create the "
            f"directory and restart. Loci is running on its built-in meta "
            f"files in the meantime, so nothing is saved to a vault."
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
                f"Vault at {vault_root} was empty and "
                f"has been seeded with meta files at v{META_VERSION}."
            )
        else:
            current = read_vault_meta_version(vault_root)
            if current is not None and current >= META_VERSION:
                return None
            if current is None and _canonical_meta_complete(vault_root):
                # A vault set up by the local wizard has a full meta/ but no
                # marker — only this path writes one. A complete meta/ is
                # evidence enough that the vault is current: adopt it and record
                # the version. create_vault_structure only writes files that are
                # missing, so it fills USER_META_FILES gaps without touching
                # anything else.
                moved = create_vault_structure(vault_root, include_siblings=False)
                write_vault_meta_version(vault_root, META_VERSION)
                # Nothing was reseeded, so there is usually nothing to say —
                # unless the adopted vault still had its overlays in meta/.
                notice = overlay_move_notice(moved)
                if notice is None:
                    return None
                print(notice, file=sys.stderr)
                return notice
            # Fills in USER_META_FILES and the skill overlays too, and moves
            # any pre-v14 overlay out of meta/: reseed_meta only rewrites the
            # canonical set, and a vault seeded before this path existed has
            # neither.
            moved = create_vault_structure(vault_root, include_siblings=False)
            reseed_meta(vault_root)
            write_vault_meta_version(vault_root, META_VERSION)
            from_version = f"v{current}" if current is not None else "unversioned"
            notice = " ".join(filter(None, [
                f"Vault meta files at {vault_root} were "
                f"automatically updated from {from_version} to v{META_VERSION}. "
                f"No action needed.",
                overlay_move_notice(moved),
            ]))

    # stderr, not stdout: visible in the server log without waiting for the
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
    # the guard covers the config.yml path too, not just the env-var one.
    with contextlib.redirect_stdout(io.StringIO()):
        return _check_meta_version()


def _check_meta_version() -> str | None:
    vault_root_env = os.environ.get("LOCI_VAULT_ROOT")
    if vault_root_env:
        return ensure_env_vault(Path(vault_root_env).expanduser())
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
    # expanduser() to match resolve_configured_root() and api._vault_root().
    # A hand-written `vault_root: ~/vault` — which prompt_vault_root's own EOF
    # message tells the user to write — otherwise passes ensure_ready()'s
    # is_dir() check against the expanded path and then reseeds into a literal
    # ./~/vault/meta relative to the cwd.
    vault_root = Path(configured_root).expanduser()
    vault_meta_version = config.get("meta_version")
    if vault_meta_version is None or vault_meta_version < META_VERSION:
        if not vault_root.is_dir():
            # The path is gone — an unmounted drive, a sync folder that has not
            # come back. Seeding would build a fresh empty vault there and
            # record it as current; leave it alone and let ensure_ready() raise
            # VAULT_UNREACHABLE, which tells the user what actually happened.
            return migration_notice
        if vault_meta_version is not None and _vault_content_missing(vault_root):
            # The config records a seed at an older version, so this vault had
            # meta files once and has none now: the directory is present but
            # empty, the shape a sync folder takes when it has remounted as a
            # placeholder. Seeding it would stamp both config and the in-vault
            # marker as current, so when the real content syncs back the reseed
            # this bump exists to deliver would never run and the user would
            # keep the stale dictionaries for good. Wait for the next startup.
            return migration_notice
        # A vault only ever opened through the HTTP UI was never seeded, so it
        # can reach this branch with no meta/ at all — reseed_meta writes into
        # that directory without creating it. This also backfills any
        # USER_META_FILES the vault predates and moves pre-v14 skill overlays
        # into skills/; reseed_meta only rewrites the canonical set. The siblings are built too, unlike ensure_env_vault
        # below: that path skips them because the operator owns the pinned
        # vault's parent. Here the parent is an ordinary user directory, and
        # init()/set_vault_root() seed it the same way —
        # skipping them would leave a vault whose meta/ is current but whose
        # loci-stage/ and assets/ never get built, and since config now reads as
        # current nothing seeds them later: the first scan_inbox fails with a
        # bare errno.
        moved = create_vault_structure(vault_root)
        reseed_meta(vault_root)
        config["meta_version"] = META_VERSION
        save_config(config)
        write_vault_meta_version(vault_root, META_VERSION)
        from_version = f"v{vault_meta_version}" if vault_meta_version is not None else "unversioned"
        return "\n".join(filter(None, [
            migration_notice,
            f"Vault meta files were automatically updated from {from_version} "
            f"to v{META_VERSION}. No action needed.",
            overlay_move_notice(moved),
        ]))
    # Config mode tracks the version in config.yml, but the vault itself may
    # later be addressed by LOCI_VAULT_ROOT (the same files, pinned by the variable).
    # Keep the in-vault marker in step so that path doesn't read the vault as
    # unversioned and reseed over the user's dictionaries.
    if read_vault_meta_version(vault_root) != META_VERSION and (vault_root / "meta").is_dir():
        write_vault_meta_version(vault_root, META_VERSION)
    return migration_notice


# ---------------------------------------------------------------------------
# Readiness
#
# The MCP server cannot prompt: it is a subprocess talking JSON-RPC over stdio,
# with no channel to the user that isn't a tool result. So a server that has no
# vault yet has to fail every vault-touching tool in a way the *model* can act
# on, and the model asks on the server's behalf. These two codes are that
# contract — they are matched on by the model, so treat them as API.
# ---------------------------------------------------------------------------

# Distinct from NOT_CONFIGURED_MESSAGE above: this one is a code the model
# matches on, not prose a human reads.
NOT_CONFIGURED = "LOCI_NOT_CONFIGURED"
VAULT_UNREACHABLE = "LOCI_VAULT_UNREACHABLE"


class VaultNotReady(RuntimeError):
    """
    Raised by ensure_ready() when no vault can be used yet.

    Raised rather than returned because the tools it guards return str, dict,
    and list[dict] alike — there is no one success shape to put an error key
    into, and a sentinel dict would have to be understood by 29 call sites.
    FastMCP surfaces the exception text to the model either way.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


_NOT_CONFIGURED_HELP = (
    "Loci has no vault configured, so there is nothing to read or write yet. "
    "Ask the user for an absolute path where their vault should live, then "
    "call set_vault_root with it. Do not guess a path and do not pick a "
    "default — the location is the user's choice, and a wrong guess puts their "
    "notes somewhere they will never look."
)


def _pinned_vault_root() -> Optional[str]:
    """The LOCI_VAULT_ROOT override, if a managed deployment set one."""
    return os.environ.get("LOCI_VAULT_ROOT") or None


def resolve_configured_root() -> tuple[Optional[Path], bool]:
    """
    Resolve the vault root without touching the filesystem.

    Returns (root, pinned). `pinned` means the root came from LOCI_VAULT_ROOT —
    a managed deployment, where the path is fixed by whoever set the variable
    and must not be changed from chat.
    """
    pinned = _pinned_vault_root()
    if pinned:
        return Path(pinned).expanduser(), True
    config = load_config() or {}
    configured = config.get("vault_root")
    if not configured:
        return None, False
    return Path(configured).expanduser(), False


# Readiness is per-vault-root, not a plain bool: the tests move
# LOCI_VAULT_ROOT between temp vaults, and set_vault_root changes it at
# runtime. Keying on the resolved path means a moved vault re-checks instead of
# reporting the previous one's state.
_ready_for: Optional[str] = None


def reset_ready_state() -> None:
    """Forget that readiness was established. For tests and set_vault_root."""
    global _ready_for
    _ready_for = None


def ensure_ready() -> Optional[str]:
    """
    Confirm a usable vault exists, seeding and upgrading it on first call.

    Returns a notice string when the first call had something to report
    (meta files seeded or upgraded), else None. Raises VaultNotReady when
    there is no vault to use.

    The work runs at most once per vault root per process — this sits in front
    of every vault-touching tool, so it has to be cheap on the 2nd call
    onwards.
    """
    global _ready_for

    root, pinned = resolve_configured_root()
    if root is None:
        raise VaultNotReady(NOT_CONFIGURED, _NOT_CONFIGURED_HELP)

    if _ready_for == str(root):
        return None

    if not root.is_dir():
        if pinned:
            raise VaultNotReady(
                VAULT_UNREACHABLE,
                f"The configured vault path {root} does not exist inside this "
                f"deployment. LOCI_VAULT_ROOT is set, so this is a managed "
                f"install and the path cannot be changed from chat. Tell the "
                f"user to create the directory or fix LOCI_VAULT_ROOT.",
            )
        raise VaultNotReady(
            VAULT_UNREACHABLE,
            f"The configured vault path {root} does not exist. It may be on a "
            f"drive that is not mounted, or in a sync folder that has not "
            f"downloaded yet. Ask the user whether to wait for that path to "
            f"come back or to point Loci somewhere else with set_vault_root — "
            f"do not silently create a new vault at a path they already chose.",
        )

    try:
        notice = check_meta_version()
    finally:
        # Record the attempt even when seeding raised. A vault we cannot write
        # to — a read-only mount, or one owned by another uid — fails the same
        # way on every call, and the caller treats that as a notice rather than
        # a failure. Without this, _ready_for is never set, so every guarded
        # tool retries the seeding and appends the same sentence to the notice
        # again. Callers that want a genuine retry call reset_ready_state().
        _ready_for = str(root)
    return notice


def set_vault_root(path: str, create: bool = True) -> dict:
    """
    Point Loci at a vault and make it usable in one call.

    Records the path, creates the directory when asked, seeds or upgrades the
    meta files, and clears the caches — so the tool call after this one works,
    with no restart. Doing only half of it (record now, seed on next use) would
    push the seeding error onto some later unrelated tool, where neither the
    user nor the model has the context to make sense of it.

    create=False adopts an existing vault and refuses anything else, writing
    nothing on the way out.

    Returns {vault_root, created, configured_at}. Raises ValueError on a path
    that cannot be used, and VaultNotReady when the deployment pins the root.
    """
    pinned = _pinned_vault_root()
    if pinned:
        raise VaultNotReady(
            VAULT_UNREACHABLE,
            f"This deployment pins the vault to {pinned} through "
            f"LOCI_VAULT_ROOT, so it cannot be changed from chat. Whoever runs "
            f"the deployment controls the path. Tell the user to change "
            f"LOCI_VAULT_ROOT instead.",
        )

    raw = (path or "").strip()
    if not raw:
        raise ValueError("A vault path is required. Ask the user where the vault should live.")
    try:
        root = Path(raw).expanduser()
    except (RuntimeError, KeyError):
        raise ValueError(f"Could not work out what {raw} expands to. Ask for a path starting with / or ~/.")
    if not root.is_absolute():
        raise ValueError(f"{root} is not an absolute path. Ask for one starting with / or ~/.")
    if root.exists() and not root.is_dir():
        raise ValueError(f"{root} is a file, not a directory. Ask for a directory path.")

    created = not root.exists()
    # create=False means "touch nothing" — not just "don't mkdir". A path that
    # exists but is not a vault is the more likely mistake of the two: seeding
    # it would put a meta/ skeleton in the user's photos folder and three new
    # directories beside it, while reporting created=False as if an existing
    # vault had been adopted.
    if not create and (created or not (root / "meta").is_dir()):
        raise ValueError(
            f"{root} is not an existing Loci vault. Confirm with the user that "
            f"it should be set up as one, then call set_vault_root again with "
            f"create=True."
        )

    # Decide before create_vault_structure() fills the gaps in.
    needs_upgrade = _meta_needs_upgrade(root)

    try:
        # print()s its way through the seeding, and under stdio that is the
        # JSON-RPC channel.
        with contextlib.redirect_stdout(io.StringIO()):
            moved_overlays = create_vault_structure(root)
            if needs_upgrade:
                # create_vault_structure only writes files that are *missing*,
                # so adopting a vault seeded at an older META_VERSION leaves its
                # dictionaries untouched. Stamping the current version on that
                # without reseeding would make every later check_meta_version()
                # see it as up to date, and the vault could never be upgraded.
                reseed_meta(root)
            write_vault_meta_version(root, META_VERSION)
    except OSError as exc:
        raise ValueError(f"Cannot set up a vault at {root}: {exc}")

    configured_at = datetime.now(timezone.utc).isoformat()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            # load_config() rather than a raw read of config_path(): it runs the
            # legacy-config migration first. Reading the destination directly
            # would write a fresh config over a pre-#65 install and drop its
            # sync_remote and created_at, stranding the old file unmigrated.
            config = load_config() or {}
            config.update({
                "vault_root": str(root),
                "meta_version": META_VERSION,
                "version": config.get("version", 1),
                "created_at": config.get("created_at", configured_at),
            })
            save_config(config)
    except OSError as exc:
        raise ValueError(
            f"The vault at {root} is set up, but its location could not be "
            f"recorded in {config_path()}: {exc}. Loci will not find it until "
            f"that file is writable."
        )

    # The registries and the graph cache a vault root of their own. Without
    # this the very next tool call answers from the vault we just left.
    reset_ready_state()
    _reset_vault_caches()

    result = {
        "vault_root": str(root),
        "created": created,
        "configured_at": configured_at,
    }
    # Adopting a pre-v14 vault moves the user's own files. This is the only
    # channel that reaches them here: the notice paths in _check_meta_version
    # never run again once this call has stamped the version as current.
    notice = overlay_move_notice(moved_overlays)
    if notice:
        result["notice"] = notice
    return result


def _reset_vault_caches() -> None:
    """Drop every singleton that has a vault root baked into it."""
    from loci.tools import nx_graph
    from loci.tools.type_registry import reset_registry
    from loci.tools.relation_registry import reset_relation_registry
    from loci.tools.scheme_registry import reset_scheme_registry

    nx_graph._graph = None
    nx_graph._built_at = 0.0
    reset_registry()
    reset_relation_registry()
    reset_scheme_registry()


def init(force: bool = False) -> dict:
    """
    Initialize Loci. Returns the active config.

    Args:
        force: If True, re-seed all meta files from references/ and bump
               meta_version in config. Does not re-run interactive setup.
    """
    existing = load_config()

    if existing and force:
        # expanduser() for the same reason _check_meta_version() does it: a
        # hand-written `vault_root: ~/vault` otherwise reseeds into a literal
        # ./~/vault/meta relative to the cwd. create_vault_structure() first
        # because reseed_meta() writes into meta/ without creating it.
        vault_root = Path(existing["vault_root"]).expanduser()
        print(f"Re-seeding meta files at {vault_root / 'meta'}...")
        create_vault_structure(vault_root)
        reseed_meta(vault_root)
        existing["meta_version"] = META_VERSION
        save_config(existing)
        print("Done.")
        return existing

    if existing and not force:
        print(f"Loci already configured. Vault root: {existing['vault_root']}")
        vault_root = Path(existing["vault_root"]).expanduser()
        print("Ensuring vault structure is complete...")
        create_vault_structure(vault_root)
        print("Done.")
        return existing

    config = setup_interactive()

    # Build the vault before saving the config, not after. A config pointing at
    # a vault that could not be created is worse than no config at all: the next
    # run takes the "already configured" branch above and fails there, with no
    # way back to the prompt short of editing the file by hand.
    vault_root = Path(config["vault_root"])
    print(f"\nCreating vault structure at {vault_root}...")
    create_vault_structure(vault_root)

    save_config(config)

    print(f"\nLoci is ready. Vault at: {vault_root}\n")
    return config


if __name__ == "__main__":  # pragma: no cover
    force = "--force" in sys.argv
    init(force=force)

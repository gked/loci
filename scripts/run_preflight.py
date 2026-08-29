"""
scripts/run_preflight.py
The preflight behind `make run`: fail before the servers start, not after.

Two misconfigurations both surface as an empty screen. An install with no
config 500s on every request, and a vault_root that is not on disk — an
unmounted drive, a sync folder that has not come down yet — serves an empty
graph with nothing on screen to say why. Both read as "the graph does not
load".

The value is resolved the way the servers resolve it, and that is the whole
point of doing this in Python rather than in the recipe:

  * load_config() parses the file with yaml.safe_load(), which strips an inline
    comment, surrounding quotes, and trailing whitespace from a hand-edited
    config. A `sed`/`tr` extraction keeps all three and then rejects a config
    the server reads fine.
  * LOCI_VAULT_ROOT short-circuits load_config() before it ever opens the file,
    so an env-var-only install has no config to require and no vault_root to
    read out of one.
  * Path.expanduser() resolves `~`, `~/vault` and `~alice/vault` alike.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

SETUP_HINT = "run: uv run setup.py"


class PreflightError(Exception):
    """A misconfiguration the user has to fix before the servers can start."""


def resolve_vault(config: Path, env_vault: str | None = None) -> Path:
    """
    The directory the servers will actually open, or PreflightError saying why
    there isn't one. Mirrors load_config() in server/tools/vault_init.py.
    """
    if env_vault and env_vault.strip():
        return Path(env_vault.strip()).expanduser()

    if not config.is_file():
        raise PreflightError(f"no Loci config at {config} — {SETUP_HINT}")

    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PreflightError(f"{config} is not valid YAML — {exc}") from exc

    raw = data.get("vault_root") if isinstance(data, dict) else None
    if raw is None or not str(raw).strip():
        raise PreflightError(f"{config} has no vault_root — {SETUP_HINT}")

    return Path(str(raw).strip()).expanduser()


def main(argv: list[str]) -> int:
    config = Path(argv[0]).expanduser() if argv else Path()

    try:
        vault = resolve_vault(config, os.environ.get("LOCI_VAULT_ROOT"))
    except PreflightError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not vault.is_dir():
        print(
            f"vault_root {vault} does not exist — unmounted drive, "
            "or a sync that has not come down?",
            file=sys.stderr,
        )
        return 1

    print(f"serving {vault}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

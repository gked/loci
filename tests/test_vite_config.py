"""
tests/test_vite_config.py
Config resolution in app/vite.config.js.

vite reads the API token out of the same config file the server writes, so
configPath() there has to mirror config_path() in vault_init.py. When it does
not, readApiToken()'s bare catch swallows the failure and the UI ships an empty
token — every /api/open-local then 403s with no diagnostic anywhere.

The config is imported in a real node process and its resolved
VITE_LOCI_TOKEN define is read back, so this exercises the file vite actually
loads rather than a copy of its logic.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

APP_DIR = Path(__file__).parent.parent / "app"

pytestmark = [
    pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed"),
    pytest.mark.skipif(
        not (APP_DIR / "node_modules" / "vite").exists(),
        reason="app/node_modules missing — run `npm ci --prefix app` (or `make test`)",
    ),
]

# defineConfig() returns the object as given, so the token is readable straight
# off the resolved define.
READ_TOKEN = """
const mod = await import(process.argv[1]);
const config = mod.default;
process.stdout.write(config.define["import.meta.env.VITE_LOCI_TOKEN"]);
"""


def _token_vite_would_use(env: dict) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", READ_TOKEN,
         str(APP_DIR / "vite.config.js")],
        cwd=APP_DIR,
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _write_config(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"api_token: {token}\n", encoding="utf-8")


def test_reads_the_token_from_the_user_level_config(tmp_path):
    _write_config(tmp_path / ".config" / "loci" / "config.yml", "user-level-token")

    assert _token_vite_would_use({"HOME": str(tmp_path)}) == "user-level-token"


def test_loci_config_expands_a_leading_tilde(tmp_path):
    """
    Python does Path(override).expanduser(); a value quoted in a shell rc or set
    in a .env arrives here with the ~ intact.
    """
    _write_config(tmp_path / "elsewhere" / "config.yml", "tilde-token")

    token = _token_vite_would_use(
        {"HOME": str(tmp_path), "LOCI_CONFIG": "~/elsewhere/config.yml"}
    )

    assert token == "tilde-token"


def test_xdg_config_home_expands_a_leading_tilde(tmp_path):
    _write_config(tmp_path / "xdg" / "loci" / "config.yml", "xdg-token")

    token = _token_vite_would_use(
        {"HOME": str(tmp_path), "XDG_CONFIG_HOME": "~/xdg"}
    )

    assert token == "xdg-token"


def test_an_explicit_token_still_wins(tmp_path):
    _write_config(tmp_path / ".config" / "loci" / "config.yml", "from-file")

    token = _token_vite_would_use(
        {"HOME": str(tmp_path), "LOCI_API_TOKEN": "from-the-environment"}
    )

    assert token == "from-the-environment"


def test_a_missing_config_yields_an_empty_token(tmp_path):
    """First run, before the server has written anything — must not throw."""
    assert _token_vite_would_use({"HOME": str(tmp_path)}) == ""

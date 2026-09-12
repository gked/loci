"""
tests/test_makefile_dev.py
The `make dev` scratch-config recipe.

Two failures this pins down, both of which hand the UI a token the API does not
have — a 403 on /api/open-local with nothing in the logs to explain it:

  1. dev spawning dev-api and dev-ui in parallel with the config as *their*
     prerequisite: on a clean checkout both generate a token and the last write
     wins, while the API has already cached the first.
  2. a failed generation still leaving a target behind: printf exits 0 with an
     empty substitution, so make never rebuilds the empty file.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="make is not installed"
)


def _make(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, **kwargs
    )


def test_dev_builds_the_config_before_forking_the_sub_makes():
    """
    Both scratch files must be prerequisites of `dev` itself. Leaving them to
    dev-api and dev-ui is the race: two sub-makes, two tokens.

    Read out of make's own database (-pRrq runs no recipes) rather than by
    running the target, which would start servers.
    """
    database = _make("-pRrq", ":")

    rules = {
        line.split(":")[0]: line.split(":", 1)[1].split()
        for line in database.stdout.splitlines()
        if line.startswith(("dev:", "dev-api:", "dev-ui:"))
    }

    assert "dev" in rules, "no `dev` rule found in the make database"
    assert rules["dev"] == rules["dev-api"] == rules["dev-ui"], (
        "dev must depend on the same scratch files as the sub-makes it forks, "
        f"got {rules}"
    )
    assert any(p.endswith("dev-config.yml") for p in rules["dev"])
    assert any(p.endswith("dev-vault") for p in rules["dev"])


def test_generating_the_dev_config_writes_a_usable_token(tmp_path):
    target = tmp_path / "dev-config.yml"

    result = _make(f"DEV_CONFIG={target}", str(target))

    assert result.returncode == 0, result.stderr
    token = yaml.safe_load(target.read_text(encoding="utf-8"))["api_token"]
    assert token and len(token) >= 32


def test_a_failed_generation_leaves_no_target_behind(tmp_path):
    """
    Without this, `api_token:` (null) gets written once and reused forever: make
    considers the target built, and every later `make dev` runs tokenless.
    """
    target = tmp_path / "dev-config.yml"

    result = _make(f"DEV_CONFIG={target}", "PATH=/nonexistent-dir", str(target))

    assert result.returncode != 0
    assert "python3" in result.stdout + result.stderr
    assert not target.exists()
    assert not target.with_suffix(".yml.tmp").exists()


def test_creating_the_dev_vault_copies_the_seed(tmp_path):
    """
    An empty vault renders a blank graph, which reads as the app being broken.
    dev-vault/ is created from the committed dev-vault-seed/ instead.
    """
    target = tmp_path / "dev-vault"

    result = _make(f"DEV_VAULT={target}", str(target))

    assert result.returncode == 0, result.stderr
    seed = sorted(p.name for p in (REPO_ROOT / "dev-vault-seed").glob("*.md"))
    assert sorted(p.name for p in target.glob("*.md")) == seed
    assert len(seed) == 500


def test_creating_the_dev_vault_leaves_no_tmp_dir_behind(tmp_path):
    target = tmp_path / "dev-vault"

    result = _make(f"DEV_VAULT={target}", str(target))

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "dev-vault.tmp").exists()


def test_a_failed_seed_copy_leaves_no_dev_vault_behind(tmp_path):
    """
    make treats an existing directory as built. An empty dev-vault/ left by a
    failed copy would have every later `make dev` serve a blank vault — the
    very symptom the seed exists to prevent — with nothing to say why.
    """
    target = tmp_path / "dev-vault"

    result = _make(f"DEV_VAULT={target}", f"DEV_VAULT_SEED={tmp_path}/no-such-seed", str(target))

    assert result.returncode != 0
    assert not target.exists()
    assert not (tmp_path / "dev-vault.tmp").exists()

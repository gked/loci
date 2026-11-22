"""
tests/test_conftest_cleanup.py
conftest.py points LOCI_CONFIG at a fresh temp folder so the suite never reads the
developer's real config. That folder must not outlive the run.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_a_pytest_run_leaves_no_temp_config_folder_behind(tmp_path):
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    env = {**os.environ, "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch)}

    # Positive control: the child must really use the scratch folder. If a platform
    # ignored the override, the folder would be made elsewhere and this test would
    # pass without checking anything.
    where = subprocess.run(
        [sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert Path(where.stdout.strip()).resolve() == scratch.resolve(), where.stdout + where.stderr

    # --collect-only is enough: conftest makes the folder at import time, so the
    # leak (or its absence) does not depend on any test running or passing.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(Path(__file__)),
         "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    left = [p.name for p in scratch.iterdir()]
    assert not [n for n in left if n.startswith("loci-test-config-")], f"the run left its config folder behind: {left}"

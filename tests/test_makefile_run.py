"""
tests/test_makefile_run.py
The `make run` target — the app against the user's real vault.

`make dev` forces LOCI_CONFIG and LOCI_VAULT_ROOT at the scratch pair so a
development run cannot write into real notes. `make run` is the other half of
that split, and its whole value is *not* overriding them: it has to read
~/.config/loci/config.yml, the file ./run_server.sh and an installed MCP server
open. A stray export on the run targets would silently serve the empty scratch
vault instead, which is exactly the "the graph does not load" report this
target exists to answer.

The preflight is pinned here too. Without it the two misconfigurations both
surface as an empty screen: no config at all (every request 500s) and a
vault_root that is not on disk (an unmounted drive, a sync folder that has not
come down) — neither of which says anything about what is wrong.
"""
import os
import shutil
import signal
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="make is not installed"
)


def _make(*args, env_overrides=None) -> subprocess.CompletedProcess:
    """
    Run make with the suite's own LOCI_* variables stripped.

    conftest.py sets LOCI_CONFIG at import and the tmp_vault fixture sets
    LOCI_VAULT_ROOT; both are inherited by a subprocess and both feed the
    resolution under test, so a leaked value would decide the result instead of
    the argument the test passed.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("LOCI_CONFIG", "LOCI_VAULT_ROOT", "XDG_CONFIG_HOME")}
    env.update(env_overrides or {})
    return subprocess.run(
        ["make", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


UNSET = "<unset>"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _recipe_env(tmp_path: Path, target: str, *overrides) -> dict[str, str]:
    """
    The environment a run/dev half actually hands its server, read out of the
    recipe rather than out of make's database.

    `make -p` prints target-specific variables under 3.81 and not under 4.x, so
    reading them there passed on macOS and failed on CI. Stubs stand in for the
    two commands the recipes exec — the value under test is what reaches them.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    out = tmp_path / "recipe-env"
    report = (
        f'printf "LOCI_CONFIG=%s\\n" "${{LOCI_CONFIG-{UNSET}}}" > "{out}"; '
        f'printf "LOCI_VAULT_ROOT=%s\\n" "${{LOCI_VAULT_ROOT-{UNSET}}}" >> "{out}"'
    )
    _stub(bin_dir, "uv", report)
    _stub(bin_dir, "npm", report)

    result = _make(
        target, *overrides,
        env_overrides={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists(), f"{target} never reached its server: {result.stdout}"
    return dict(
        line.split("=", 1) for line in out.read_text().splitlines() if line
    )


def test_run_targets_do_not_override_the_config_or_the_vault(tmp_path):
    """
    The one thing `make run` must not do. If either variable reaches the
    servers, run serves the scratch vault and the target is pointless.

    The halves are what carry the environment; `run` only forks these two.
    NODE_MODULES stands in for the install so the stubbed npm is not asked to
    populate app/node_modules.
    """
    stamp = tmp_path / "installed"
    stamp.touch()

    for target in ("run-api", "run-ui"):
        env = _recipe_env(tmp_path, target, "RUN_CHECKED=1", f"NODE_MODULES={stamp}")

        assert env["LOCI_CONFIG"] == UNSET, (
            f"{target} sets LOCI_CONFIG, so it would not read the real config"
        )
        assert env["LOCI_VAULT_ROOT"] == UNSET, (
            f"{target} sets LOCI_VAULT_ROOT, so it would serve the scratch vault"
        )


def test_dev_targets_still_override_both(tmp_path):
    """
    The counterweight: proof the assertion above is meaningful, and that adding
    run did not disturb the isolation dev depends on. DEV_CONFIG and DEV_VAULT
    are pointed at scratch paths that already exist, so the real ones are
    neither built nor read.
    """
    config = tmp_path / "dev-config.yml"
    config.write_text("api_token: abc123\n", encoding="utf-8")
    vault = tmp_path / "dev-vault"
    vault.mkdir()

    for target in ("dev-api", "dev-ui"):
        env = _recipe_env(
            tmp_path, target, f"DEV_CONFIG={config}", f"DEV_VAULT={vault}"
        )

        assert env["LOCI_CONFIG"] == str(config), f"{target} lost its scratch config"
        assert env["LOCI_VAULT_ROOT"] == str(vault), f"{target} lost its scratch vault"


def test_every_run_target_runs_the_preflight_first():
    """
    Including the halves run alone: `make run-api` on an unconfigured machine
    should say so, not serve 500s.
    """
    database = _make("-pRrq", ":").stdout
    rules = {
        line.split(":")[0]: line.split(":", 1)[1].split()
        for line in database.splitlines()
        if line.startswith(("run:", "run-api:", "run-ui:"))
    }
    assert set(rules) == {"run", "run-api", "run-ui"}, (
        f"a run target was renamed or removed: found {sorted(rules)}"
    )
    for target, prereqs in rules.items():
        assert "run-check" in prereqs, f"{target} skips the preflight"


def test_preflight_reports_a_missing_config(tmp_path):
    missing = tmp_path / "config.yml"

    result = _make(f"RUN_CONFIG={missing}", "run-check")

    assert result.returncode != 0
    assert str(missing) in result.stderr
    assert "setup.py" in result.stderr


def test_preflight_reports_a_config_with_no_vault_root(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text("api_token: abc123\n", encoding="utf-8")

    result = _make(f"RUN_CONFIG={config}", "run-check")

    assert result.returncode != 0
    assert "no vault_root" in result.stderr


def test_preflight_reports_a_vault_root_that_is_not_on_disk(tmp_path):
    """
    The failure this target exists to make legible: the config is fine, the
    directory is not there, and every earlier symptom was an empty graph.
    """
    absent = tmp_path / "unmounted-drive" / "vault"
    config = tmp_path / "config.yml"
    config.write_text(f"vault_root: {absent}\n", encoding="utf-8")

    result = _make(f"RUN_CONFIG={config}", "run-check")

    assert result.returncode != 0
    assert str(absent) in result.stderr
    assert "does not exist" in result.stderr


def test_preflight_passes_and_names_the_vault_it_will_serve(tmp_path):
    vault = tmp_path / "knowledge-vault"
    vault.mkdir()
    config = tmp_path / "config.yml"
    config.write_text(f"vault_root: {vault}\napi_token: abc123\n", encoding="utf-8")

    result = _make(f"RUN_CONFIG={config}", "run-check")

    assert result.returncode == 0, result.stderr
    assert str(vault) in result.stdout


def test_preflight_expands_a_leading_tilde_in_the_vault_root(tmp_path):
    """
    Path.expanduser() resolves a hand-written `~/vault` server-side, so the
    preflight has to as well, quotes and all. The finer cases live in
    test_run_preflight.py; this one pins the wiring through make.
    """
    home = tmp_path / "home"
    (home / "vault").mkdir(parents=True)
    config = tmp_path / "config.yml"
    config.write_text('vault_root: "~/vault"\n', encoding="utf-8")

    result = _make(f"RUN_CONFIG={config}", "run-check", env_overrides={"HOME": str(home)})

    assert result.returncode == 0, result.stderr
    assert str(home / "vault") in result.stdout


def test_preflight_needs_no_config_file_when_the_env_vault_root_is_set(tmp_path):
    """
    load_config() short-circuits on LOCI_VAULT_ROOT before it opens the config,
    so this install serves fine and demanding the file only blocked it.
    """
    vault = tmp_path / "from-the-environment"
    vault.mkdir()

    result = _make(
        f"RUN_CONFIG={tmp_path / 'nothing-here.yml'}", "run-check",
        env_overrides={"LOCI_VAULT_ROOT": str(vault)},
    )

    assert result.returncode == 0, result.stderr
    assert str(vault) in result.stdout


def test_preflight_checks_the_env_vault_root_when_one_is_set(tmp_path):
    """
    LOCI_VAULT_ROOT short-circuits load_config(), so it is the path the server
    will actually open — checking the config's value there would pass on a
    vault nothing is going to serve.
    """
    vault = tmp_path / "configured"
    vault.mkdir()
    config = tmp_path / "config.yml"
    config.write_text(f"vault_root: {vault}\n", encoding="utf-8")
    absent = tmp_path / "from-the-environment"

    result = _make(
        f"RUN_CONFIG={config}", "run-check",
        env_overrides={"LOCI_VAULT_ROOT": str(absent)},
    )

    assert result.returncode != 0
    assert str(absent) in result.stderr


def test_run_stops_the_other_half_when_one_of_them_exits(tmp_path):
    """
    A bare `wait` waits for both children, so a dead API left the UI serving a
    proxy to nothing and the shell blocked on it — the port-already-in-use case
    looked exactly like the blank screen the preflight exists to prevent.

    Stubs stand in for the two halves: uv fails at once (the API), npm sleeps
    (the UI). The target has to come back anyway.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "uv", "exit 1")
    _stub(bin_dir, "npm", "sleep 60")

    env = {k: v for k, v in os.environ.items()
           if k not in ("LOCI_CONFIG", "LOCI_VAULT_ROOT", "XDG_CONFIG_HOME")}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    # start_new_session, because the recipe's shutdown is a `kill 0` on its own
    # process group: without it the group is pytest's.
    process = subprocess.Popen(
        ["make", "run", "RUN_CHECKED=1"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        output = process.communicate(timeout=30)[0]
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        pytest.fail("`make run` kept waiting after one half exited")

    assert "stopping run-ui too" in output

"""The inbox plan lock works on every platform.

inbox_plan used to `import fcntl` at module top. fcntl does not exist on
Windows, so the import failed there and took every inbox tool with it
(scan_inbox, the plan tools, the loci-inbox skill), plus anything that merely
imports inbox_scanner. The lock now picks its primitive by platform.
"""

import errno
import importlib.util
import subprocess
import sys
import textwrap
import time
import types
from pathlib import Path

import pytest

from loci.tools import inbox_plan

MODULE_PATH = Path(inbox_plan.__file__)


def _load_as_windows(monkeypatch, fake_msvcrt):
    """A private copy of inbox_plan imported the way Windows would import it:
    no fcntl, a (fake) msvcrt, sys.platform == "win32"."""
    monkeypatch.setitem(sys.modules, "fcntl", None)  # `import fcntl` -> ImportError
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(sys, "platform", "win32")
    spec = importlib.util.spec_from_file_location("inbox_plan_as_windows", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_msvcrt(busy_attempts: int = 0):
    calls = []
    state = {"busy": busy_attempts}

    def locking(fd, mode, nbytes):
        calls.append((mode, nbytes))
        if mode == fake.LK_NBLCK and state["busy"] > 0:
            state["busy"] -= 1
            raise OSError(errno.EACCES, "Permission denied")

    fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=locking, calls=calls)
    return fake


def test_the_module_imports_without_fcntl(monkeypatch):
    module = _load_as_windows(monkeypatch, _fake_msvcrt())
    assert hasattr(module, "_plan_lock")


def test_windows_takes_a_one_byte_lock_and_releases_it(monkeypatch, tmp_path):
    fake = _fake_msvcrt()
    module = _load_as_windows(monkeypatch, fake)
    with module._plan_lock(tmp_path):
        assert fake.calls == [(fake.LK_NBLCK, 1)]
    assert fake.calls == [(fake.LK_NBLCK, 1), (fake.LK_UNLCK, 1)]


def test_windows_waits_for_a_lock_another_process_holds(monkeypatch, tmp_path):
    fake = _fake_msvcrt(busy_attempts=3)
    module = _load_as_windows(monkeypatch, fake)
    with module._plan_lock(tmp_path):
        pass
    attempts = [c for c in fake.calls if c[0] == fake.LK_NBLCK]
    assert len(attempts) == 4  # three refusals, then the lock


def test_windows_does_not_swallow_a_real_error(monkeypatch, tmp_path):
    fake = _fake_msvcrt()

    def broken(fd, mode, nbytes):
        if mode == fake.LK_NBLCK:
            raise OSError(errno.EINVAL, "Invalid lock operation")
        raise OSError(errno.EACCES, "No lock to release")

    fake.locking = broken
    module = _load_as_windows(monkeypatch, fake)
    with pytest.raises(OSError) as raised:
        with module._plan_lock(tmp_path):
            pass
    assert raised.value.errno == errno.EINVAL


def test_the_lock_excludes_a_second_process(tmp_path):
    """Real locks on this OS: a child holds the plan lock, the contender must wait."""
    ready = tmp_path / "holder-ready"
    holder_code = textwrap.dedent(
        """
        import sys, time
        from pathlib import Path
        from loci.tools.inbox_plan import _plan_lock
        with _plan_lock(Path(sys.argv[1])):
            Path(sys.argv[2]).write_text("held", encoding="utf-8")
            time.sleep(1.5)
        """
    )
    contender_code = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from loci.tools.inbox_plan import _plan_lock
        with _plan_lock(Path(sys.argv[1])):
            print("acquired", flush=True)
        """
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(tmp_path), str(ready)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    contender = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            if holder.poll() is not None:
                _, stderr = holder.communicate()
                pytest.fail(f"lock holder exited before acquiring the lock: {stderr}")
            if time.monotonic() >= deadline:
                pytest.fail("timed out waiting for the child to acquire the lock")
            time.sleep(0.01)

        contender = subprocess.Popen(
            [sys.executable, "-c", contender_code, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started = time.monotonic()
        try:
            stdout, stderr = contender.communicate(timeout=10)
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(
                "timed out waiting for the second process to acquire the lock"
            ) from exc

        waited = time.monotonic() - started
        assert contender.returncode == 0, stderr
        assert stdout.strip() == "acquired"
        assert waited >= 1.0, f"got the lock after {waited:.2f}s while another process held it"
    finally:
        for proc in (contender, holder):
            if proc is None:
                continue
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=2)

"""
tests/test_fs_retry.py
Windows refuses to write, rename over or delete a file another program has open
(an editor, a sync client, a virus scan): PermissionError, gone in milliseconds.
The vault's writes wait for it there, and only there.
"""

from pathlib import Path

import pytest

from loci import api
from loci.tools import fs_retry, inbox_plan


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    return slept


def busy_times(monkeypatch, owner, name, times, only_suffix=None):
    """Make `owner.name` raise PermissionError the first `times` times it is called for
    a path ending in `only_suffix` (any path when None), then behave."""
    real = getattr(owner, name)
    calls = []

    def flaky(*args, **kwargs):
        target = str(args[0]) if args else ""
        if only_suffix is None or target.endswith(only_suffix):
            calls.append(1)
            if len(calls) <= times:
                raise PermissionError(13, "Access is denied")
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, flaky)
    return calls


def on_windows(monkeypatch, yes=True):
    monkeypatch.setattr(fs_retry.sys, "platform", "win32" if yes else "linux")


def test_a_busy_file_is_retried_on_windows(monkeypatch, no_sleep):
    on_windows(monkeypatch)
    calls = []

    def action():
        calls.append(1)
        if len(calls) < 4:
            raise PermissionError(13, "Access is denied")
        return "done"

    assert fs_retry.retry_busy(action) == "done"
    assert len(calls) == 4 and len(no_sleep) == 3


def test_a_file_that_stays_busy_raises_after_exactly_the_bounded_attempts(monkeypatch, no_sleep):
    on_windows(monkeypatch)
    calls = []

    def action():
        calls.append(1)
        raise PermissionError(13, "Access is denied")

    with pytest.raises(PermissionError):
        fs_retry.retry_busy(action)
    assert len(calls) == fs_retry.ATTEMPTS


def test_a_permission_error_is_not_retried_elsewhere(monkeypatch, no_sleep):
    on_windows(monkeypatch, yes=False)
    calls = []

    def action():
        calls.append(1)
        raise PermissionError(13, "Permission denied")

    with pytest.raises(PermissionError):
        fs_retry.retry_busy(action)
    assert len(calls) == 1 and no_sleep == []


def test_other_errors_are_never_retried(monkeypatch, no_sleep):
    on_windows(monkeypatch)
    calls = []

    def action():
        calls.append(1)
        raise FileNotFoundError("gone")

    with pytest.raises(FileNotFoundError):
        fs_retry.retry_busy(action)
    assert len(calls) == 1


def test_write_text_keeps_utf_8_and_lf_across_a_retry(tmp_path, monkeypatch, no_sleep):
    on_windows(monkeypatch)
    calls = busy_times(monkeypatch, Path, "write_text", times=2)
    target = tmp_path / "note.md"

    fs_retry.write_utf8(target, "line one\nПривет ✓\n")

    assert len(calls) == 3
    assert target.read_bytes() == "line one\nПривет ✓\n".encode("utf-8")      # no CRLF


# --- the vault's own writes -------------------------------------------------------

def save(title):
    return api.save(type="document", title=title, body="hello",
                    extra_fields={"status": "draft", "subtype": "note"})


def test_saving_a_note_waits_for_a_file_that_is_briefly_open(tmp_vault, monkeypatch, no_sleep):
    on_windows(monkeypatch)
    calls = busy_times(monkeypatch, Path, "write_text", times=3, only_suffix="retry-title.md")

    saved = save("Retry Title")

    assert len(calls) == 4
    assert Path(saved["path"]).is_file()


def test_patching_a_note_waits_for_a_file_that_is_briefly_open(tmp_vault, monkeypatch, no_sleep):
    saved = save("Patch Retry")
    on_windows(monkeypatch)
    calls = busy_times(monkeypatch, Path, "write_text", times=2, only_suffix="patch-retry.md")

    api.patch(saved["uid"], {"summary": "after the retry"})

    assert len(calls) == 3
    assert "after the retry" in Path(saved["path"]).read_text(encoding="utf-8")


def test_a_note_that_stays_open_still_fails_the_save_on_windows(tmp_vault, monkeypatch, no_sleep):
    on_windows(monkeypatch)
    busy_times(monkeypatch, Path, "write_text", times=10_000, only_suffix="stuck-note.md")
    with pytest.raises(PermissionError):
        save("Stuck Note")


def test_the_inbox_plan_waits_for_a_plan_file_that_is_briefly_open(tmp_path, monkeypatch, no_sleep):
    on_windows(monkeypatch)
    target = tmp_path / ".inbox-plan.yaml"
    target.write_text("old", encoding="utf-8")
    calls = busy_times(monkeypatch, inbox_plan.os, "replace", times=3)

    inbox_plan._atomic_write(target, "new")

    assert len(calls) == 4
    assert target.read_text(encoding="utf-8") == "new"
    assert not target.with_suffix(".yaml.tmp").exists()


def test_restoring_a_deleted_node_waits_for_a_file_that_is_briefly_open(tmp_vault, monkeypatch, no_sleep):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")      # off by default in the suite
    saved = save("Undo Retry")
    path = Path(saved["path"])
    api.patch(saved["uid"], {"summary": "changed"})
    on_windows(monkeypatch)
    calls = busy_times(monkeypatch, Path, "write_bytes", times=2, only_suffix="undo-retry.md")

    api.undo_last_change()

    assert len(calls) == 3
    assert "changed" not in path.read_text(encoding="utf-8")

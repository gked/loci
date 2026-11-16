"""Vault files are written with LF on every platform.

Opening a file in text mode translates "\\n" to "\\r\\n" on Windows. A vault is
meant to be shared between machines (Nextcloud, Syncthing), so a note saved on
Windows must be byte-identical to the same note saved on a Mac. Git for Windows
ships core.autocrlf=true, which hides the difference from `git status` but not
from the sync client or from anything that reads the blobs.

The bytes also matter to Loci itself: vault_history finds a deleted node by the
`uid:` line in its old blob, and that match used to stop at the "\\r".

Windows' default is simulated by patching Path.write_text, so these run on any OS.
"""

from pathlib import Path

import pytest

from loci import api
from loci.tools import vault_history


@pytest.fixture
def windows_newlines(monkeypatch):
    real_write_text = Path.write_text

    def write_text(self, data, encoding=None, errors=None, newline=None):
        return real_write_text(
            self, data, encoding=encoding, errors=errors,
            newline="\r\n" if newline is None else newline,
        )

    monkeypatch.setattr(Path, "write_text", write_text)


def _save(title="Line ending probe"):
    return api.save(
        "document", title, "first line\nsecond line\n",
        tags=["windows"], domains=["technology-engineering"], summary="probe",
        extra_fields={"subtype": "note", "status": "draft"},
    )


def test_a_saved_node_is_written_with_lf(tmp_vault, windows_newlines):
    saved = _save()
    assert b"\r" not in Path(saved["path"]).read_bytes()


def test_a_patched_node_stays_lf(tmp_vault, windows_newlines):
    saved = _save()
    api.patch(saved["uid"], {"summary": "changed"}, body="new body\nline two\n")
    assert b"\r" not in Path(saved["path"]).read_bytes()


def test_write_meta_is_lf(tmp_vault, windows_newlines):
    path = Path(api.write_meta("tag-dictionary", "# tags\nwindows — the OS\n"))
    assert b"\r" not in path.read_bytes()


def test_a_skill_overlay_is_lf(tmp_vault, windows_newlines):
    path = Path(api.write_skill("- rule one\n- rule two\n", skill="loci-save"))
    assert b"\r" not in path.read_bytes()


def test_the_uid_line_matches_whatever_the_line_ending():
    """Vaults written by 0.8.1 on Windows hold CRLF blobs that must still be found."""
    for ending in (b"\n", b"\r\n"):
        header = b"type: document" + ending + b"uid: abcd1234" + ending + b"title: x" + ending
        match = vault_history._UID_LINE.search(header)
        assert match and match.group(1) == b"abcd1234", repr(ending)


@pytest.fixture
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    yield
    vault_history.set_source("api")


@pytest.fixture
def legacy_crlf_writer(monkeypatch):
    """The 0.8.1 writer on Windows: every write is CRLF, whatever newline= says."""
    real_write_text = Path.write_text

    def write_text(self, data, encoding=None, errors=None, newline=None):
        return real_write_text(self, data, encoding=encoding, errors=errors, newline="\r\n")

    monkeypatch.setattr(Path, "write_text", write_text)


def test_a_deleted_node_with_a_crlf_only_history_is_still_found_by_uid(tmp_vault, history_on, legacy_crlf_writer):
    """A vault 0.8.1 wrote on Windows holds CRLF in every blob; the restore must still work."""
    saved = _save("Deleted with CRLF")
    assert b"\r\n" in Path(saved["path"]).read_bytes()
    deleted = api.delete(saved["uid"])
    result = api.restore(saved["uid"], f"{deleted['commit']}~1")
    assert result["was_deleted"]
    assert "first line" in api.get(saved["uid"])

"""
A note renamed or moved outside Loci: the watcher records one "Renamed: old.md →
new.md" commit, and the history of the node (by uid) joins the commits of every
path the note has had.
"""

import sys

import pytest

from loci import api
from loci.tools import vault_history


@pytest.fixture(autouse=True)
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    vault_history._uid_index.clear()
    yield
    vault_history.set_source("api")


def node(tmp_vault, title, body="hello"):
    uid = api.save(type="document", title=title, body=body,
                   extra_fields={"status": "draft", "subtype": "note"})["uid"]
    return uid, api._resolve_vault_path(uid)


def _message(tmp_vault, commit):
    repo = vault_history._open(tmp_vault)
    return repo[vault_history._resolve(repo, commit)].message.decode()


def subjects(tmp_vault, ref):
    return [c["subject"] for c in api.history(ref)]


def test_a_rename_is_one_commit_with_a_clear_subject(tmp_vault):
    uid, path = node(tmp_vault, "Old name")
    new = path.with_name("brand-new-name.md")
    path.rename(new)
    commit = vault_history.snapshot_outside(tmp_vault)
    assert commit
    top = vault_history.history(tmp_vault, new.name)[0]
    assert top["subject"] == f"Renamed: {path.name} → {new.name}"


def test_the_history_by_uid_spans_a_rename(tmp_vault):
    uid, path = node(tmp_vault, "Travelling note")
    new = path.with_name("moved-note.md")
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    seen = subjects(tmp_vault, uid)
    assert any(s.startswith("Renamed:") for s in seen)
    assert len(seen) >= 2, seen         # the commit that made the note, and the rename
    # By the new path too, because the uid is read from the file
    assert subjects(tmp_vault, new.name) == seen


def test_a_move_into_a_folder_is_a_rename(tmp_vault):
    uid, path = node(tmp_vault, "Folder move")
    (tmp_vault / "archive").mkdir()
    new = tmp_vault / "archive" / path.name
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    assert subjects(tmp_vault, uid)[0] == f"Renamed: {path.name} → archive/{path.name}"


def test_a_delete_and_an_add_with_different_uids_is_not_a_rename(tmp_vault):
    uid, path = node(tmp_vault, "Goes away")
    other_uid, other = node(tmp_vault, "Stays")
    path.unlink()
    (tmp_vault / "fresh.md").write_text(other.read_text().replace(other_uid, "abcdef12"))
    vault_history.snapshot_outside(tmp_vault)
    assert subjects(tmp_vault, "fresh.md")[0] == vault_history.OUTSIDE_MESSAGE


def test_a_copy_is_not_a_rename(tmp_vault):
    uid, path = node(tmp_vault, "Copied")
    copy = path.with_name("copy-of-it.md")
    copy.write_text(path.read_text())
    vault_history.snapshot_outside(tmp_vault)
    assert subjects(tmp_vault, "copy-of-it.md")[0] == vault_history.OUTSIDE_MESSAGE


def test_a_rename_together_with_an_edit_in_one_burst(tmp_vault):
    uid, path = node(tmp_vault, "Renamed and edited")
    other_uid, other = node(tmp_vault, "Edited only")
    new = path.with_name("renamed-and-edited-2.md")
    path.rename(new)
    new.write_text(new.read_text() + "\nmore words\n")                 # renamed and edited
    other.write_text(other.read_text() + "\nand here\n")               # edited only
    vault_history.snapshot_outside(tmp_vault)
    c = vault_history.history(tmp_vault, new.name)[0]
    assert c["subject"] == f"Renamed: {path.name} → {new.name}"
    assert vault_history.history(tmp_vault, other.name)[0]["commit"] == c["commit"]
    assert "Also changed outside Loci: 1 other file." in _message(tmp_vault, c["commit"])


def test_the_diff_of_a_commit_from_before_the_rename_still_works(tmp_vault):
    uid, path = node(tmp_vault, "Diff across")
    first = vault_history.history(tmp_vault, path)[-1]["commit"]
    new = path.with_name("diff-across-2.md")
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    assert "Diff across" in api.diff(uid, first)
    assert "Diff across" in api.get(uid, commit=first)


def test_undo_refuses_a_rename_commit(tmp_vault):
    uid, path = node(tmp_vault, "No undo")
    path.rename(path.with_name("no-undo-2.md"))
    vault_history.snapshot_outside(tmp_vault)
    with pytest.raises(vault_history.HistoryError):
        vault_history.head_changes(tmp_vault)


def test_a_burst_that_names_both_paths_finds_the_rename(tmp_vault):
    uid, path = node(tmp_vault, "Watcher rename")
    new = path.with_name("watcher-rename-2.md")
    path.rename(new)
    # What the watcher passes: the paths the file events named.
    assert vault_history.snapshot_outside(tmp_vault, [path, new])
    assert subjects(tmp_vault, uid)[0] == f"Renamed: {path.name} → {new.name}"


def test_another_note_that_takes_the_old_name_is_not_in_the_history(tmp_vault):
    uid, path = node(tmp_vault, "First owner")
    other_uid, other = node(tmp_vault, "Second owner")
    new = path.with_name("first-owner-moved.md")
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    # A different note now sits at the name the first one had.
    path.write_text(other.read_text().replace(other_uid, "abcdef12"))
    vault_history.snapshot_outside(tmp_vault)
    taker = vault_history.history(tmp_vault, path.name, limit=1)[0]["commit"]
    mine = [c["commit"] for c in api.history(uid)]
    assert taker not in mine
    assert any(s.startswith("Renamed:") for s in subjects(tmp_vault, uid))


def test_the_history_by_an_old_path_spans_the_rename(tmp_vault):
    uid, path = node(tmp_vault, "Asked by old name")
    new = path.with_name("asked-by-old-name-2.md")
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    assert not path.exists()
    assert subjects(tmp_vault, path.name) == subjects(tmp_vault, uid)


@pytest.mark.skipif(sys.platform == "win32", reason="NTFS cannot hold a newline in a file name")
def test_a_new_name_with_a_newline_keeps_the_subject_on_one_line(tmp_vault):
    uid, path = node(tmp_vault, "Odd name")
    new = path.with_name("odd\nname.md")
    path.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    subject = subjects(tmp_vault, uid)[0]
    assert subject.startswith("Renamed: ") and "odd?name.md" in subject


def test_a_name_that_is_not_utf8_still_makes_a_message():
    assert vault_history._name_in_message(b"a\xff\nb.md") == "a�?b.md"
    vault_history._name_in_message(b"a\xff.md").encode("utf-8")      # does not raise

"""
restore_vault for a commit from before a rename: the node comes back at the
path it has now, and a name that another note held at that commit is never
mistaken for it.
"""

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


def node(title, body="hello"):
    uid = api.save(type="document", title=title, body=body,
                   extra_fields={"status": "draft", "subtype": "note"})["uid"]
    return uid, api._resolve_vault_path(uid)


def commit_of(path):
    return api.history(path.name)[0]["commit"]


def test_a_commit_from_before_the_rename_restores_at_the_new_path(tmp_vault):
    uid, old = node("Moved around", body="the original words")
    before = commit_of(old)
    new = old.with_name("moved-around-2.md")
    old.rename(new)
    new.write_text(new.read_text().replace("the original words", "damaged"))
    vault_history.snapshot_outside(tmp_vault)

    out = api.restore(uid, before)

    assert out["restored"] and out["path"] == str(new)
    assert "the original words" in new.read_text()
    assert not old.exists()                                    # the old path is not recreated


def test_a_renamed_then_deleted_node_comes_back_at_its_last_path(tmp_vault):
    uid, old = node("Gone after a move", body="keep this")
    before = commit_of(old)
    new = old.with_name("gone-after-a-move-2.md")
    old.rename(new)
    vault_history.snapshot_outside(tmp_vault)
    api.delete(uid)
    assert not new.exists()

    out = api.restore(uid, before)

    assert out["was_deleted"] and out["path"] == str(new)
    assert "keep this" in new.read_text()


def test_a_name_another_note_held_then_is_not_taken_for_this_node(tmp_vault):
    other_uid, other = node("Name taker", body="other node")
    taken = other.name
    other_commit = commit_of(other)
    api.delete(other_uid)
    # Our node lives at another path first, then moves onto the name the other held.
    uid, first = node("Wanderer", body="wanderer words")
    wanderer_commit = commit_of(first)
    first.rename(first.with_name(taken))
    vault_history.snapshot_outside(tmp_vault)
    now = tmp_vault / taken

    api.restore(uid, wanderer_commit)
    assert "wanderer words" in now.read_text()

    # The other node's commit holds the name too, but not this node: refuse, change nothing.
    before = now.read_text()
    with pytest.raises(vault_history.HistoryError):
        api.restore(uid, other_commit)
    assert now.read_text() == before


def test_an_ordinary_restore_still_works(tmp_vault):
    uid, path = node("Plain", body="first")
    good = commit_of(path)
    api.patch(uid, {}, body="second")
    api.restore(uid, good)
    assert "first" in path.read_text()

"""
A node deleted on one computer and edited on another keeps the edit. The history
says so, the app warns on the node while that is its newest change, and the user
can delete the node again (and only then).
"""

import time

import pytest

from loci import api
from loci.tools import node_merge, vault_history
from loci.tools.frontmatter import load_frontmatter

from test_http_server import TOKEN, auth, client  # noqa: F401  (fixtures)
from test_node_merge import BASE, as_computer, diverge, history_on  # noqa: F401  (fixtures)


@pytest.fixture
def auth_headers(auth):
    return {"X-Loci-Token": TOKEN, "Origin": "http://localhost:5173"}


@pytest.fixture
def restored(tmp_vault, as_computer):
    """A node whose delete lost to an edit: (uid, path)."""
    node, copy = diverge(tmp_vault, as_computer, b=BASE + "edited\n")
    uid = str(load_frontmatter(node.read_text())[0]["uid"])       # not split by hand: an all-digit uid is quoted
    node.unlink()
    node_merge.resolve(tmp_vault, copy.name)
    return uid, node


def test_the_history_names_the_overridden_delete(restored):
    uid, node = restored
    found = api.overridden_delete(uid)
    assert found["subject"].startswith(node_merge.OVERRIDE_SUBJECT)
    assert found["subject"].endswith(node.name)
    assert api.overridden_delete(node.name)["commit"] == found["commit"]    # by path too


def test_an_ordinary_node_is_not_flagged(tmp_vault):
    saved = api.save(type="document", title="Plain", body="x", extra_fields={"status": "draft", "subtype": "note"})
    assert api.overridden_delete(saved["uid"]) is None
    assert api.overridden_delete("00000000") is None             # unknown node: no error


def test_a_later_change_clears_the_warning(restored):
    uid, _ = restored
    assert api.overridden_delete(uid)
    time.sleep(1.1)                  # commits are told apart by the second
    api.patch(uid, {"summary": "kept on purpose"})
    assert api.overridden_delete(uid) is None


def test_delete_again_removes_the_node(restored):
    uid, node = restored
    out = api.delete_overridden(uid)
    assert out["deleted"] is True
    assert not node.exists()
    assert api.overridden_delete(uid) is None                     # the newest change is now a delete


def test_delete_again_refuses_an_ordinary_node(tmp_vault):
    saved = api.save(type="document", title="Keep me", body="x", extra_fields={"status": "draft", "subtype": "note"})
    with pytest.raises(ValueError):
        api.delete_overridden(saved["uid"])
    assert api.overridden_delete(saved["uid"]) is None
    assert api.get(saved["uid"])                                  # still there


def test_http_reports_and_deletes(client, restored, auth_headers):
    uid, node = restored
    assert client.get(f"/api/nodes/{uid}/overridden-delete").json()["overridden"] is True
    assert client.post(f"/api/nodes/{uid}/delete-again").status_code in (401, 403)   # no token
    assert node.exists()
    done = client.post(f"/api/nodes/{uid}/delete-again", headers=auth_headers)
    assert done.status_code == 200 and not node.exists()


def test_the_newest_commit_is_found_across_utc_offsets(tmp_vault, monkeypatch):
    """Two computers write dates with their own offset; text order is not time order."""
    later_east = {"commit": "a", "date": "2026-11-14T12:00:05+05:00", "subject": "Edit"}      # 07:00:05 UTC
    earlier_west = {"commit": "b", "date": "2026-11-14T03:00:00-05:00",                       # 08:00:00 UTC
                    "subject": f"{node_merge.OVERRIDE_SUBJECT} x.md"}
    monkeypatch.setattr(api, "_resolve_vault_path", lambda p: tmp_vault)
    monkeypatch.setattr(api, "history", lambda p, n=20: [later_east, earlier_west])
    assert api.overridden_delete("x")["commit"] == "b"            # by text, "12:00:05+05:00" would win


def test_http_delete_again_of_an_unknown_node_is_404(client, tmp_vault, auth_headers):
    assert client.post("/api/nodes/00000000/delete-again", headers=auth_headers).status_code == 404


def test_http_refuses_delete_again_for_an_ordinary_node(client, tmp_vault, auth_headers):
    saved = api.save(type="document", title="Not overridden", body="x", extra_fields={"status": "draft", "subtype": "note"})
    r = client.post(f"/api/nodes/{saved['uid']}/delete-again", headers=auth_headers)
    assert r.status_code == 409
    assert client.get(f"/api/nodes/{saved['uid']}/overridden-delete").json() == {"overridden": False}

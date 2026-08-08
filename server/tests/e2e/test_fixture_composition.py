"""
server/tests/e2e/test_fixture_composition.py
Pins the shape of the e2e vault.

This is the canary. If someone adds, removes, or re-tags a fixture node, this
file fails with a specific message instead of five UI specs failing with
confusing off-by-N counts. When it fails, update vault_facts.py.
"""

import json
import urllib.error
import urllib.request
from collections import Counter

import pytest

import vault_facts as vf

# Every spec here asserts on the e2e fixture vault, so none of them can pass
# against a deployment. See README "Running against a deployment".
pytestmark = pytest.mark.fixture_bound


def _api(base_url: str, path: str):
    with urllib.request.urlopen(f"{base_url}{path}") as r:
        return json.load(r)


def _status(base_url: str, path: str) -> int:
    try:
        with urllib.request.urlopen(f"{base_url}{path}") as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_total_node_count(base_url):
    nodes = _api(base_url, "/api/graph")["nodes"]
    assert len(nodes) == vf.TOTAL_GRAPH_NODES


def test_file_backed_node_count(base_url):
    nodes = _api(base_url, "/api/nodes?state=all")
    assert len([n for n in nodes if n.get("path")]) == vf.TOTAL_FILES


def test_default_visible_count(base_url):
    nodes = _api(base_url, "/api/nodes?state=all")
    visible = [n for n in nodes if n.get("state") != "archived" and n.get("path")]
    assert len(visible) == vf.DEFAULT_VISIBLE


def test_archived_and_ghost_uids(base_url):
    nodes = _api(base_url, "/api/nodes?state=all")
    assert sorted(n["uid"] for n in nodes if n.get("state") == "archived") == sorted(vf.ARCHIVED_UIDS)
    assert sorted(n["uid"] for n in nodes if not n.get("path")) == sorted(vf.GHOST_UIDS)


def test_type_counts(base_url):
    nodes = _api(base_url, "/api/nodes?state=all")
    visible = [n for n in nodes if n.get("state") != "archived" and n.get("path")]
    assert dict(Counter(n["type"] for n in visible)) == vf.TYPE_COUNTS


def test_tag_counts(base_url):
    """
    Compares the whole tag histogram, not just the keys we already know about —
    otherwise adding a fixture node with a brand-new tag would change the rail
    without failing anything here, which is exactly what this canary exists to
    catch.
    """
    nodes = _api(base_url, "/api/nodes?state=all")
    visible = [n for n in nodes if n.get("state") != "archived" and n.get("path")]
    counts = Counter(t for n in visible for t in (n.get("tags") or []))
    assert dict(counts) == vf.TAG_COUNTS


def test_search_fixtures_behave(base_url):
    hits = _api(base_url, f"/api/search?q={vf.SEARCH_HIT}")
    assert len(hits) == vf.SEARCH_HIT_COUNT
    assert hits[0]["uid"] == vf.SEARCH_HIT_UID
    assert len(_api(base_url, f"/api/search?q={vf.SEARCH_MISS}")) == 0


def test_declared_openable_uids_really_open(base_url):
    """Every uid in OPENABLE_UIDS must actually resolve — specs depend on it."""
    broken = [u for u in vf.OPENABLE_UIDS if _status(base_url, f"/api/nodes/{u}") != 200]
    assert not broken, f"OPENABLE_UIDS contains uids that 404: {broken}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN FIXTURE DEFECT: api.get() resolves a bare uid via `[0-9a-f]{8}` "
        "(server/api.py:194), matching generate_uid()'s hex output. 14 base "
        "fixture nodes use mnemonic uids with non-hex letters (srch0001, "
        "hub00001, spoke001, ...) and therefore 404. Real vaults are unaffected. "
        "Fixing means renaming uids across ~20 Python test files. When that "
        "happens this xfail turns XPASS and strict=True fails the run — delete "
        "it and UNRESOLVABLE_UID_COUNT then."
    ),
)
def test_every_file_backed_node_is_openable(base_url):
    nodes = _api(base_url, "/api/nodes?state=all")
    file_backed = [n["uid"] for n in nodes if n.get("path")]
    broken = [u for u in file_backed if _status(base_url, f"/api/nodes/{u}") != 200]
    assert not broken, f"{len(broken)} nodes cannot be opened: {sorted(broken)}"


def test_unresolvable_uid_count_is_unchanged(base_url):
    """
    Pins the size of the defect above. If it shrinks, someone is mid-fix and
    should finish the job; if it grows, a new bad fixture uid slipped in.
    """
    nodes = _api(base_url, "/api/nodes?state=all")
    file_backed = [n["uid"] for n in nodes if n.get("path")]
    broken = [u for u in file_backed if _status(base_url, f"/api/nodes/{u}") != 200]
    assert len(broken) == vf.UNRESOLVABLE_UID_COUNT, (
        f"expected {vf.UNRESOLVABLE_UID_COUNT} unresolvable uids, got "
        f"{len(broken)}: {sorted(broken)}"
    )

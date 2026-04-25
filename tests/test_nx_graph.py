"""
tests/test_nx_graph.py
Tests for tools/nx_graph.py: mutation functions (index_node, index_edges,
drop_node, neighbors) and the lazy-build get() path.

The read functions (find, related, path, search) are covered by
test_retrieval.py via the YAML-parametrized suite.
"""

import networkx as nx
import pytest

import nx_graph as g


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _node_attrs(**overrides) -> dict:
    base = dict(
        type="document", title="", tags=[], domains=[], summary="",
        language="", aliases=[], path="", status="",
        due_date="", created_at="", updated_at="",
    )
    base.update(overrides)
    return base


@pytest.fixture
def live_graph(monkeypatch):
    """
    Inject a small known DiGraph as the singleton.
    n001 → n002 (relates-to)
    n003 has no edges (isolated)
    """
    dg = nx.DiGraph()
    dg.add_node("n001", **_node_attrs(type="document", title="Alpha"))
    dg.add_node("n002", **_node_attrs(type="task",     title="Beta",  status="open"))
    dg.add_node("n003", **_node_attrs(type="topic",    title="Gamma"))
    dg.add_edge("n001", "n002", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    return g


@pytest.fixture
def null_graph(monkeypatch):
    """Singleton is None — all mutations must be silent no-ops."""
    monkeypatch.setattr(g, "_graph", None)
    return g


# ---------------------------------------------------------------------------
# index_node
# ---------------------------------------------------------------------------

def test_index_node_noop_when_graph_none(null_graph):
    null_graph.index_node("x001", type="document", title="X")
    assert null_graph._graph is None


def test_index_node_adds_new_node(live_graph):
    live_graph.index_node("new001", type="article", title="New Node", tags=["fresh"])
    assert live_graph._graph.has_node("new001")
    assert live_graph._graph.nodes["new001"]["title"] == "New Node"
    assert live_graph._graph.nodes["new001"]["tags"] == ["fresh"]


def test_index_node_updates_existing_node(live_graph):
    live_graph.index_node("n001", title="Alpha Updated", tags=["updated"])
    assert live_graph._graph.nodes["n001"]["title"] == "Alpha Updated"
    assert live_graph._graph.nodes["n001"]["tags"] == ["updated"]
    # type not passed → unchanged
    assert live_graph._graph.nodes["n001"]["type"] == "document"


def test_index_node_partial_update_preserves_other_attrs(live_graph):
    live_graph.index_node("n002", status="done")
    assert live_graph._graph.nodes["n002"]["status"] == "done"
    assert live_graph._graph.nodes["n002"]["title"] == "Beta"  # untouched


# ---------------------------------------------------------------------------
# index_edges
# ---------------------------------------------------------------------------

def test_index_edges_noop_when_graph_none(null_graph):
    null_graph.index_edges("n001", [{"uid": "n002", "type": "belongs-to"}])
    assert null_graph._graph is None


def test_index_edges_adds_edges(live_graph):
    live_graph.index_edges("n003", [{"uid": "n001", "type": "about"}])
    assert live_graph._graph.has_edge("n003", "n001")
    assert live_graph._graph.edges["n003", "n001"]["rel_type"] == "about"


def test_index_edges_replaces_existing_edges(live_graph):
    # n001 → n002 exists; replace with n001 → n003
    live_graph.index_edges("n001", [{"uid": "n003", "type": "parent-of"}])
    assert not live_graph._graph.has_edge("n001", "n002")
    assert live_graph._graph.has_edge("n001", "n003")
    assert live_graph._graph.edges["n001", "n003"]["rel_type"] == "parent-of"


def test_index_edges_empty_relations_removes_all_outgoing(live_graph):
    live_graph.index_edges("n001", [])
    assert list(live_graph._graph.out_edges("n001")) == []


def test_index_edges_none_relations_removes_all_outgoing(live_graph):
    live_graph.index_edges("n001", None)
    assert list(live_graph._graph.out_edges("n001")) == []


def test_index_edges_skips_entries_missing_uid(live_graph):
    live_graph.index_edges("n003", [{"type": "about"}])  # no uid key
    assert list(live_graph._graph.out_edges("n003")) == []


def test_index_edges_multiple_relations(live_graph):
    live_graph.index_edges("n001", [
        {"uid": "n002", "type": "relates-to"},
        {"uid": "n003", "type": "parent-of"},
    ])
    assert live_graph._graph.has_edge("n001", "n002")
    assert live_graph._graph.has_edge("n001", "n003")


# ---------------------------------------------------------------------------
# drop_node
# ---------------------------------------------------------------------------

def test_drop_node_noop_when_graph_none(null_graph):
    null_graph.drop_node("n001")
    assert null_graph._graph is None


def test_drop_node_removes_node(live_graph):
    live_graph.drop_node("n001")
    assert not live_graph._graph.has_node("n001")


def test_drop_node_removes_incident_edges(live_graph):
    # n001 → n002 exists; dropping n001 removes that edge
    live_graph.drop_node("n001")
    assert not live_graph._graph.has_edge("n001", "n002")


def test_drop_node_noop_for_nonexistent_uid(live_graph):
    live_graph.drop_node("ghost000")  # should not raise
    assert live_graph._graph.number_of_nodes() == 3


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------

def test_neighbors_returns_empty_when_graph_none(null_graph):
    assert null_graph.neighbors("n001") == []


def test_neighbors_returns_empty_for_unknown_uid(live_graph):
    assert live_graph.neighbors("ghost000") == []


def test_neighbors_outgoing_direction(live_graph):
    result = live_graph.neighbors("n001")
    out = [r for r in result if r["direction"] == "out"]
    assert len(out) == 1
    assert out[0]["uid"] == "n002"
    assert out[0]["rel_type"] == "relates-to"
    assert out[0]["type"] == "task"


def test_neighbors_incoming_direction(live_graph):
    # n001 → n002, so n002 should see n001 as an incoming neighbor
    result = live_graph.neighbors("n002")
    incoming = [r for r in result if r["direction"] == "in"]
    assert len(incoming) == 1
    assert incoming[0]["uid"] == "n001"
    assert incoming[0]["rel_type"] == "relates-to"


def test_neighbors_isolated_node_returns_empty(live_graph):
    assert live_graph.neighbors("n003") == []


def test_neighbors_includes_title_and_type(live_graph):
    result = live_graph.neighbors("n001")
    assert result[0]["title"] == "Beta"
    assert result[0]["type"] == "task"


# ---------------------------------------------------------------------------
# get — lazy build
# ---------------------------------------------------------------------------

def test_get_builds_graph_from_vault(tmp_vault, monkeypatch):
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)
    graph_obj = g.get(tmp_vault)
    assert graph_obj is not None
    assert graph_obj.number_of_nodes() > 0


def test_get_returns_same_instance_on_repeated_calls(tmp_vault, monkeypatch):
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)
    first = g.get(tmp_vault)
    second = g.get(tmp_vault)
    assert first is second


def test_get_skips_meta_files(tmp_vault, monkeypatch):
    """Files under meta/ should not be indexed as nodes."""
    meta_file = tmp_vault / "meta" / "type-dictionary.md"
    meta_file.parent.mkdir(exist_ok=True)
    meta_file.write_text(
        "---\nuid: metaonly\ntype: document\ntitle: Should Not Index\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)
    graph_obj = g.get(tmp_vault)
    assert not graph_obj.has_node("metaonly")


def test_get_ignores_files_without_uid(tmp_vault, monkeypatch):
    (tmp_vault / "no-uid.md").write_text(
        "---\ntype: document\ntitle: No UID\n---\n\nBody.", encoding="utf-8"
    )
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)
    graph_obj = g.get(tmp_vault)
    # Node should not appear since it has no uid
    titles = [graph_obj.nodes[n]["title"] for n in graph_obj.nodes]
    assert "No UID" not in titles


def test_get_rebuilds_when_file_added_outside_session(tmp_vault, monkeypatch):
    """
    A file created after the initial build (simulating a write from another
    process or session) must be picked up automatically on the next get() call.

    _built_at is backdated to 0.0 after the first build so the staleness check
    always fires regardless of filesystem mtime resolution (avoids HFS+ 1-second
    granularity flakiness on slow or legacy volumes).
    """
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)

    first = g.get(tmp_vault)
    initial_count = first.number_of_nodes()

    # Backdate _built_at so any current mtime will be seen as newer — filesystem
    # resolution (1 s on HFS+, nanoseconds on APFS/tmpfs) becomes irrelevant.
    monkeypatch.setattr(g, "_built_at", 0.0)

    # Write a new vault file directly (bypassing index_node, as an external write would)
    (tmp_vault / "auto-detected.md").write_text(
        "---\nuid: autodet01\ntype: document\ntitle: Auto Detected\ntags: []\n"
        "relations: []\nsummary: Added outside session.\n---\n\nBody.",
        encoding="utf-8",
    )

    second = g.get(tmp_vault)
    assert second.number_of_nodes() == initial_count + 1
    assert second.has_node("autodet01")


def test_get_does_not_rebuild_when_vault_unchanged(tmp_vault, monkeypatch):
    """No file changes → same graph instance returned on repeated calls."""
    monkeypatch.setattr(g, "_graph", None)
    monkeypatch.setattr(g, "_built_at", 0.0)
    first = g.get(tmp_vault)
    second = g.get(tmp_vault)
    assert first is second


# ---------------------------------------------------------------------------
# _vault_dir_mtime
# ---------------------------------------------------------------------------

def test_vault_dir_mtime_increases_after_new_file(tmp_path):
    from nx_graph import _vault_dir_mtime
    vault = tmp_path / "vault"
    vault.mkdir()
    before = _vault_dir_mtime(vault)
    (vault / "new.md").write_text("hello", encoding="utf-8")
    after = _vault_dir_mtime(vault)
    assert after >= before


def test_vault_dir_mtime_checks_subdirectories(tmp_path):
    from nx_graph import _vault_dir_mtime
    vault = tmp_path / "vault"
    vault.mkdir()
    subdir = vault / "tasks"
    subdir.mkdir()
    before = _vault_dir_mtime(vault)
    (subdir / "new.md").write_text("hello", encoding="utf-8")
    after = _vault_dir_mtime(vault)
    assert after >= before


# ---------------------------------------------------------------------------
# _parse_frontmatter — edge cases
# ---------------------------------------------------------------------------

def test_parse_frontmatter_no_frontmatter_marker(tmp_path):
    """File that doesn't start with --- → returns None."""
    from nx_graph import _parse_frontmatter
    p = tmp_path / "plain.md"
    p.write_text("Just plain text\n", encoding="utf-8")
    assert _parse_frontmatter(p) is None


def test_parse_frontmatter_incomplete_delimiter(tmp_path):
    """File with opening --- but no closing --- → len(parts) < 3 → returns None."""
    from nx_graph import _parse_frontmatter
    p = tmp_path / "bad-fm.md"
    p.write_text("---\nno closing delimiter\n", encoding="utf-8")
    assert _parse_frontmatter(p) is None


def test_parse_frontmatter_exception_returns_none(tmp_path):
    """Non-UTF-8 file raises UnicodeDecodeError inside the try block → returns None."""
    from nx_graph import _parse_frontmatter
    p = tmp_path / "binary.md"
    p.write_bytes(b"\xff\xfe\x80\x81 not utf-8")
    assert _parse_frontmatter(p) is None


# ---------------------------------------------------------------------------
# related — additional coverage
# ---------------------------------------------------------------------------

def test_related_null_graph_returns_empty(null_graph):
    assert null_graph.related("n001") == []


def test_related_unknown_uid_returns_empty(live_graph):
    assert live_graph.related("unknown_uid") == []


# ---------------------------------------------------------------------------
# path — null graph, undirected fallback, no path
# ---------------------------------------------------------------------------

def test_path_null_graph_returns_empty(null_graph):
    assert null_graph.path("n001", "n002") == []


def test_path_undirected_fallback(live_graph):
    """n001 → n002 exists; reverse direction n002 → n001 requires undirected fallback."""
    result = live_graph.path("n002", "n001")
    assert len(result) == 2
    assert result[0]["uid"] == "n002"
    assert result[-1]["uid"] == "n001"


def test_path_no_path_returns_empty(live_graph):
    """n001 and n003 are not connected — no directed or undirected path."""
    assert live_graph.path("n001", "n003") == []


# ---------------------------------------------------------------------------
# find — null graph, related_to, date filters
# ---------------------------------------------------------------------------

def test_find_null_graph_returns_empty(null_graph):
    assert null_graph.find(node_type="task") == []


def test_find_related_to_known_uid(live_graph):
    """related_to=n001 should return n002 (successor) and exclude n003 (isolated)."""
    result = live_graph.find(related_to="n001")
    uids = [r["uid"] for r in result]
    assert "n002" in uids
    assert "n003" not in uids


def test_find_related_to_unknown_uid_returns_empty(live_graph):
    assert live_graph.find(related_to="no_such_uid") == []


def test_find_related_to_excludes_non_adjacent(live_graph):
    """n003 is isolated; related_to=n001 must not include it."""
    result = live_graph.find(related_to="n001")
    uids = [r["uid"] for r in result]
    assert "n003" not in uids


def test_find_due_after_filter(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("t001", **_node_attrs(title="Old Task", due_date="2024-01-01"))
    dg.add_node("t002", **_node_attrs(title="New Task", due_date="2026-01-01"))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.find(due_after="2025-01-01")
    uids = [r["uid"] for r in result]
    assert "t002" in uids
    assert "t001" not in uids


def test_find_created_after_filter(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("c001", **_node_attrs(title="Old Doc", created_at="2024-06-01T00:00:00Z"))
    dg.add_node("c002", **_node_attrs(title="New Doc", created_at="2026-06-01T00:00:00Z"))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.find(created_after="2025-01-01")
    uids = [r["uid"] for r in result]
    assert "c002" in uids
    assert "c001" not in uids


def test_find_updated_after_filter(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("u001", **_node_attrs(title="Stale", updated_at="2024-01-01T00:00:00Z"))
    dg.add_node("u002", **_node_attrs(title="Fresh", updated_at="2026-01-01T00:00:00Z"))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.find(updated_after="2025-01-01")
    uids = [r["uid"] for r in result]
    assert "u002" in uids
    assert "u001" not in uids


# ---------------------------------------------------------------------------
# search — alias match, null graph
# ---------------------------------------------------------------------------

def test_search_null_graph_returns_empty(null_graph):
    assert null_graph.search("alpha") == []


def test_search_alias_match(monkeypatch):
    """Query that matches an alias but not title or summary."""
    dg = nx.DiGraph()
    dg.add_node(
        "a001",
        **_node_attrs(type="topic", title="Machine Learning", aliases=["ML", "deep learning"]),
    )
    monkeypatch.setattr(g, "_graph", dg)
    result = g.search("deep learning")
    assert any(r["uid"] == "a001" for r in result)


# ---------------------------------------------------------------------------
# recent
# ---------------------------------------------------------------------------

def test_recent_null_graph_returns_empty(null_graph):
    assert null_graph.recent() == []


def test_recent_includes_nodes_within_window(monkeypatch):
    from datetime import datetime, timezone, timedelta
    recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dg = nx.DiGraph()
    dg.add_node("r001", **_node_attrs(title="Fresh", updated_at=recent_date, status="open"))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.recent(days=30)
    assert any(r["uid"] == "r001" for r in result)


def test_recent_excludes_nodes_outside_window(monkeypatch):
    from datetime import datetime, timezone, timedelta
    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dg = nx.DiGraph()
    dg.add_node("r002", **_node_attrs(title="Stale", updated_at=old_date))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.recent(days=30)
    assert not any(r["uid"] == "r002" for r in result)


def test_recent_excludes_nodes_without_updated_at(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("r003", **_node_attrs(title="No Date", updated_at=""))
    monkeypatch.setattr(g, "_graph", dg)
    assert g.recent(days=30) == []


def test_recent_sorted_newest_first(monkeypatch):
    from datetime import datetime, timezone, timedelta
    newer = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    older = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dg = nx.DiGraph()
    dg.add_node("r004", **_node_attrs(title="Newer", updated_at=newer))
    dg.add_node("r005", **_node_attrs(title="Older", updated_at=older))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.recent(days=30)
    assert result[0]["uid"] == "r004"
    assert result[1]["uid"] == "r005"


def test_recent_respects_limit(monkeypatch):
    from datetime import datetime, timezone, timedelta
    recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dg = nx.DiGraph()
    for i in range(5):
        dg.add_node(f"r{i:03d}", **_node_attrs(title=f"Node {i}", updated_at=recent_date))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.recent(days=30, limit=3)
    assert len(result) == 3


def test_recent_return_shape(monkeypatch):
    from datetime import datetime, timezone, timedelta
    recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dg = nx.DiGraph()
    dg.add_node("r006", **_node_attrs(type="task", title="My Task", updated_at=recent_date, status="todo"))
    monkeypatch.setattr(g, "_graph", dg)
    result = g.recent(days=30)
    assert len(result) == 1
    assert set(result[0].keys()) == {"uid", "title", "type", "path", "updated_at", "status"}
    assert result[0]["status"] == "todo"


# ---------------------------------------------------------------------------
# insights
# ---------------------------------------------------------------------------

def test_insights_null_graph_returns_empty(null_graph):
    assert null_graph.insights() == []


def test_insights_excludes_nodes_without_domains(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("i001", **_node_attrs(title="No Domains"))
    dg.add_node("i002", **_node_attrs(title="Other", domains=["science-research"]))
    dg.add_edge("i001", "i002", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    result = g.insights()
    assert not any(r["uid"] == "i001" for r in result)


def test_insights_excludes_nodes_with_no_cross_domain_neighbors(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("i003", **_node_attrs(title="Eng A", domains=["technology-engineering"]))
    dg.add_node("i004", **_node_attrs(title="Eng B", domains=["technology-engineering"]))
    dg.add_edge("i003", "i004", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    result = g.insights()
    assert not any(r["uid"] == "i003" for r in result)


def test_insights_includes_cross_domain_bridge(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("i005", **_node_attrs(title="Bridge", domains=["technology-engineering"]))
    dg.add_node("i006", **_node_attrs(title="Personal", domains=["personal-development"]))
    dg.add_edge("i005", "i006", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    result = g.insights()
    bridge = next((r for r in result if r["uid"] == "i005"), None)
    assert bridge is not None
    assert "personal-development" in bridge["connects_to_domains"]


def test_insights_return_shape(monkeypatch):
    dg = nx.DiGraph()
    dg.add_node("i007", **_node_attrs(title="Bridge", domains=["technology-engineering"]))
    dg.add_node("i008", **_node_attrs(title="Other", domains=["philosophy-ethics"]))
    dg.add_edge("i007", "i008", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    result = g.insights()
    assert len(result) >= 1
    item = next(r for r in result if r["uid"] == "i007")
    assert set(item.keys()) == {"uid", "title", "type", "domains", "connects_to_domains", "degree"}


def test_insights_respects_limit(monkeypatch):
    dg = nx.DiGraph()
    personal = "personal-development"
    for i in range(5):
        dg.add_node(f"hub{i:02d}", **_node_attrs(title=f"Hub {i}", domains=["technology-engineering"]))
        dg.add_node(f"nb{i:02d}", **_node_attrs(title=f"Nb {i}", domains=[personal]))
        dg.add_edge(f"hub{i:02d}", f"nb{i:02d}", rel_type="relates-to")
    monkeypatch.setattr(g, "_graph", dg)
    result = g.insights(limit=3)
    assert len(result) == 3

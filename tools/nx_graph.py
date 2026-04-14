"""
tools/nx_graph.py
NetworkX-backed in-memory graph index for the Loci vault.

This module is intentionally prefixed nx_ to make the backend explicit.
When migrating to Kuzu, swap this file for kuzu_graph.py and update the
import in api.py — no other changes needed.

The graph is a module-level singleton, lazily built on first call to get().
It is rebuilt from scratch on each server startup (no persistence).
The vault markdown files are the source of truth.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import networkx as nx
import yaml

_graph: Optional[nx.DiGraph] = None
_vault_root: Optional[Path] = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> Optional[dict]:
    """Parse YAML frontmatter from a markdown file. Returns None on failure."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return None


def _build(vault_root: Path) -> nx.DiGraph:
    """
    Scan all vault markdown files and build a DiGraph.
    Nodes carry: type, title, tags, domains, summary, path.
    Edges carry: rel_type.
    """
    g = nx.DiGraph()

    for md_file in vault_root.rglob("*.md"):
        # Skip meta files — they are not vault items
        if md_file.parent.name == "meta":
            continue

        fm = _parse_frontmatter(md_file)
        if not fm or "uid" not in fm:
            continue

        uid = fm["uid"]
        g.add_node(
            uid,
            type=fm.get("type", ""),
            title=fm.get("title", ""),
            tags=fm.get("tags") or [],
            domains=fm.get("domains") or [],
            summary=fm.get("summary", ""),
            language=fm.get("language", ""),
            aliases=fm.get("aliases") or [],
            path=str(md_file),
        )

        for rel in fm.get("relations") or []:
            target_uid = rel.get("uid")
            rel_type = rel.get("type", "")
            if target_uid:
                g.add_edge(uid, target_uid, rel_type=rel_type)

    return g


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(vault_root: Path) -> nx.DiGraph:
    """Return the graph, building it lazily on first call."""
    global _graph, _vault_root
    with _lock:
        if _graph is None:
            _vault_root = vault_root
            _graph = _build(vault_root)
    return _graph


def index_node(uid: str, **attrs) -> None:
    """Add or update a node's attributes. Creates the node if it doesn't exist."""
    g = _graph
    if g is None:
        return
    if g.has_node(uid):
        g.nodes[uid].update(attrs)
    else:
        g.add_node(uid, **attrs)


def index_edges(uid: str, relations: list) -> None:
    """
    Replace all outgoing edges from uid with new ones derived from relations.
    relations: list of {uid: str, type: str} dicts (vault frontmatter format).
    """
    g = _graph
    if g is None:
        return
    # Remove all existing outgoing edges
    g.remove_edges_from(list(g.out_edges(uid)))
    # Add new edges
    for rel in relations or []:
        target_uid = rel.get("uid")
        rel_type = rel.get("type", "")
        if target_uid:
            g.add_edge(uid, target_uid, rel_type=rel_type)


def drop_node(uid: str) -> None:
    """Remove a node and all its incident edges."""
    g = _graph
    if g is None:
        return
    if g.has_node(uid):
        g.remove_node(uid)


def neighbors(uid: str) -> list[dict]:
    """
    Return direct neighbors of uid with edge metadata.
    Includes both successors (outgoing) and predecessors (incoming).
    """
    g = _graph
    if g is None or not g.has_node(uid):
        return []

    result = []
    for target in g.successors(uid):
        attrs = g.nodes[target]
        edge = g.edges[uid, target]
        result.append({
            "uid": target,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "rel_type": edge.get("rel_type", ""),
            "direction": "out",
        })
    for source in g.predecessors(uid):
        attrs = g.nodes[source]
        edge = g.edges[source, uid]
        result.append({
            "uid": source,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "rel_type": edge.get("rel_type", ""),
            "direction": "in",
        })
    return result


def related(uid: str, depth: int = 2) -> list[dict]:
    """
    Return all nodes within `depth` hops of uid (ego graph).
    Result includes distance from the origin node, excludes the origin itself.
    """
    g = _graph
    if g is None or not g.has_node(uid):
        return []

    ego = nx.ego_graph(g, uid, radius=depth, undirected=True)
    g_undirected = g.to_undirected()
    result = []
    for node in ego.nodes:
        if node == uid:
            continue
        try:
            distance = nx.shortest_path_length(g_undirected, uid, node)
        except nx.NetworkXNoPath:
            distance = None
        attrs = ego.nodes[node]
        result.append({
            "uid": node,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "distance": distance,
        })
    return sorted(result, key=lambda x: (x["distance"] or 99, x["title"]))


def path(uid_from: str, uid_to: str) -> list[dict]:
    """
    Return the shortest path between two nodes as an ordered list.
    Returns an empty list if no path exists.
    """
    g = _graph
    if g is None:
        return []
    try:
        node_ids = nx.shortest_path(g, uid_from, uid_to)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        try:
            node_ids = nx.shortest_path(g.to_undirected(), uid_from, uid_to)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
    return [
        {
            "uid": n,
            "title": g.nodes[n].get("title", ""),
            "type": g.nodes[n].get("type", ""),
        }
        for n in node_ids
    ]


def find(node_type: str = None, tag: str = None) -> list[dict]:
    """
    Filter nodes by type and/or tag.
    Returns list of {uid, title, type, path}.
    """
    g = _graph
    if g is None:
        return []

    result = []
    for uid, attrs in g.nodes(data=True):
        if node_type and attrs.get("type") != node_type:
            continue
        if tag and tag not in (attrs.get("tags") or []):
            continue
        result.append({
            "uid": uid,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "path": attrs.get("path", ""),
        })
    return sorted(result, key=lambda x: x["title"])


def search(query: str) -> list[dict]:
    """
    Case-insensitive substring search across node titles and summaries.
    Returns list of {uid, title, type, path, summary}.
    """
    g = _graph
    if g is None:
        return []

    q = query.lower()
    result = []
    for uid, attrs in g.nodes(data=True):
        title = attrs.get("title", "")
        summary = attrs.get("summary", "") or ""
        aliases = attrs.get("aliases") or []
        alias_text = " ".join(aliases).lower()
        if q in title.lower() or q in summary.lower() or q in alias_text:
            result.append({
                "uid": uid,
                "title": title,
                "type": attrs.get("type", ""),
                "path": attrs.get("path", ""),
                "summary": summary,
            })
    return sorted(result, key=lambda x: x["title"])

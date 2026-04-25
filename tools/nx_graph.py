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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import networkx as nx
import yaml

_graph: Optional[nx.DiGraph] = None
_vault_root: Optional[Path] = None
_built_at: float = 0.0  # vault dir mtime observed at last build
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


def _date_str(val) -> str:
    """Normalise a frontmatter date value to an ISO string. YAML parses bare
    dates (e.g. 2024-01-15) as datetime.date objects, so we stringify them."""
    return str(val) if val else ""


def _vault_dir_mtime(vault_root: Path) -> float:
    """
    Return the most recent mtime across vault_root and its immediate subdirectories.
    Creating or deleting a file updates the containing directory's mtime, so this
    is a cheap O(subdirs) staleness signal — no need to stat every .md file.
    """
    latest = vault_root.stat().st_mtime
    for entry in vault_root.iterdir():
        if entry.is_dir():
            latest = max(latest, entry.stat().st_mtime)
    return latest


def _build(vault_root: Path) -> nx.DiGraph:
    """
    Scan all vault markdown files and build a DiGraph.
    Nodes carry: type, title, tags, domains, summary, status, date fields, path.
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
            status=fm.get("status", ""),
            due_date=_date_str(fm.get("due_date")),
            created_at=_date_str(fm.get("created_at")),
            updated_at=_date_str(fm.get("updated_at")),
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
    """
    Return the graph, building (or rebuilding) as needed.

    Rebuilds when:
    - the graph has never been built (_graph is None), or
    - any directory under vault_root has a newer mtime than when the graph
      was last built, indicating files were added or removed outside this
      server process.
    """
    global _graph, _vault_root, _built_at
    with _lock:
        current_mtime = _vault_dir_mtime(vault_root)
        if _graph is None or current_mtime > _built_at:
            _vault_root = vault_root
            _graph = _build(vault_root)
            _built_at = current_mtime
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
        except nx.NetworkXNoPath:  # pragma: no cover
            distance = None  # pragma: no cover
        attrs = ego.nodes[node]
        result.append({
            "uid": node,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "distance": distance,
            "summary": attrs.get("summary", ""),
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


def find(
    node_type: str = None,
    tag: str = None,
    status: str = None,
    due_before: str = None,
    due_after: str = None,
    created_after: str = None,
    updated_after: str = None,
    related_to: str = None,
    language: str = None,
) -> list[dict]:
    """
    Filter nodes by any combination of supported attributes.
    All parameters are optional; at least one should be provided.
    Returns list of {uid, title, type, path, status, due_date, language}.

    Date parameters accept ISO date strings (YYYY-MM-DD).
    related_to: uid — only return nodes connected to this uid by any edge.
    """
    g = _graph
    if g is None:
        return []

    # Pre-compute the neighbor set once when related_to is given.
    related_uids: set | None = None
    if related_to:
        if g.has_node(related_to):
            related_uids = set(g.successors(related_to)) | set(g.predecessors(related_to))
        else:
            return []

    result = []
    for uid, attrs in g.nodes(data=True):
        if node_type and attrs.get("type") != node_type:
            continue
        if tag and tag not in (attrs.get("tags") or []):
            continue
        if status and attrs.get("status") != status:
            continue
        if language and attrs.get("language") != language:
            continue
        if related_uids is not None and uid not in related_uids:
            continue

        node_due = attrs.get("due_date", "")
        if due_before and not (node_due and node_due <= due_before):
            continue
        if due_after and not (node_due and node_due >= due_after):
            continue

        node_created = attrs.get("created_at", "")
        if created_after and not (node_created and node_created >= created_after):
            continue

        node_updated = attrs.get("updated_at", "")
        if updated_after and not (node_updated and node_updated >= updated_after):
            continue

        result.append({
            "uid": uid,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "path": attrs.get("path", ""),
            "status": attrs.get("status", ""),
            "due_date": attrs.get("due_date", ""),
            "language": attrs.get("language", ""),
        })
    return sorted(result, key=lambda x: x["title"])


def recent(days: int = 30, limit: int = 20) -> list[dict]:
    """
    Return the most recently updated vault nodes within the last N days.
    Sorted by updated_at descending. Nodes without updated_at are excluded.
    Returns list of {uid, title, type, path, updated_at, status}.
    """
    g = _graph
    if g is None:
        return []

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    result = []
    for uid, attrs in g.nodes(data=True):
        updated = attrs.get("updated_at", "")
        if updated and updated[:10] >= cutoff_date:
            result.append({
                "uid": uid,
                "title": attrs.get("title", ""),
                "type": attrs.get("type", ""),
                "path": attrs.get("path", ""),
                "updated_at": updated,
                "status": attrs.get("status", ""),
            })
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result[:limit]


def insights(limit: int = 10) -> list[dict]:
    """
    Surface vault nodes that bridge different domains — connected to nodes from
    domains other than their own. Sorted by breadth of cross-domain reach.
    Returns list of {uid, title, type, domains, connects_to_domains, degree}.
    """
    g = _graph
    if g is None:
        return []

    result = []
    for uid, attrs in g.nodes(data=True):
        own_domains = set(attrs.get("domains") or [])
        if not own_domains:
            continue

        neighbor_domains: set = set()
        for nb in list(g.successors(uid)) + list(g.predecessors(uid)):
            neighbor_domains.update(g.nodes[nb].get("domains") or [])

        # Nodes with multiple own domains require a neighbor outside ALL of them to qualify.
        cross = neighbor_domains - own_domains
        if cross:
            result.append({
                "uid": uid,
                "title": attrs.get("title", ""),
                "type": attrs.get("type", ""),
                "domains": sorted(own_domains),
                "connects_to_domains": sorted(cross),
                "degree": g.degree(uid),
            })

    result.sort(key=lambda x: (len(x["connects_to_domains"]), x["degree"]), reverse=True)
    return result[:limit]


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
        if q in title.lower() or q in summary.lower() or any(q in alias.lower() for alias in aliases):
            result.append({
                "uid": uid,
                "title": title,
                "type": attrs.get("type", ""),
                "path": attrs.get("path", ""),
                "summary": summary,
            })
    return sorted(result, key=lambda x: x["title"])

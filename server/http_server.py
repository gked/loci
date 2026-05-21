"""
server/http_server.py
HTTP REST API for the Loci vault — serves the React frontend.

Run with:
    uv run uvicorn server.http_server:app --reload --port 8765
"""
from __future__ import annotations

import logging
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Add server/ and server/tools/ to path so we can import api.py and its deps
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from vault_init import load_config
import nx_graph as graph
import api as vault_api

log = logging.getLogger(__name__)

_VAULT_ROOT: Path | None = None


def _resolve_vault_root() -> Path:
    config = load_config()
    if not config:
        raise RuntimeError("Loci is not configured. Run: python tools/vault_init.py")
    return Path(config["vault_root"]).expanduser()


def _vault_root() -> Path:
    if _VAULT_ROOT is not None:
        return _VAULT_ROOT
    return _resolve_vault_root()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _VAULT_ROOT
    try:
        _VAULT_ROOT = _resolve_vault_root()
        graph.get(_VAULT_ROOT)
    except Exception as e:
        log.warning("Graph pre-warm failed: %s", e)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _parse_file(raw: str) -> dict:
    """
    Parse api.get() output into {frontmatter: dict, body: str, asset: dict | None}.

    api.get() returns a markdown string with YAML frontmatter. When the node has
    has_asset: true, asset info is appended in one of two formats:
      - Text asset: second --- block followed by file content
      - Binary/large asset: plain key: value lines appended to body
    """
    result: dict = {"frontmatter": {}, "body": "", "asset": None}
    if not raw.startswith("---"):
        result["body"] = raw
        return result

    parts = raw.split("---", 2)
    if len(parts) < 3:
        return result

    try:
        result["frontmatter"] = yaml.safe_load(parts[1]) or {}
    except Exception:
        pass

    remainder = parts[2]

    # Text asset case: embedded second --- block with asset info + content
    m = re.search(
        r'\n\n---\nasset_path: (.+)\nasset_mime_type: (.+)\nasset_size_bytes: (\d+)\n---\n\n([\s\S]*)$',
        remainder,
    )
    if m:
        result["body"] = remainder[: m.start()].strip()
        result["asset"] = {
            "path": m.group(1).strip(),
            "mime_type": m.group(2).strip(),
            "size_bytes": int(m.group(3)),
            "content": m.group(4),
        }
        return result

    # Binary/large asset case: plain key: value lines appended after body
    m2 = re.search(
        r'\n\nasset_path: (.+)\nasset_mime_type: (.+)\nasset_size_bytes: (\d+)$',
        remainder,
    )
    if m2:
        result["body"] = remainder[: m2.start()].strip()
        result["asset"] = {
            "path": m2.group(1).strip(),
            "mime_type": m2.group(2).strip(),
            "size_bytes": int(m2.group(3)),
            "content": None,
        }
        return result

    result["body"] = remainder.strip()
    return result


# ---------------------------------------------------------------------------
# Endpoints — /api/nodes/recent must be registered before /api/nodes/{uid}
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    try:
        vr = _vault_root()
        g = graph.get(vr)
        return {"status": "ok", "vault_root": str(vr), "node_count": g.number_of_nodes()}
    except Exception as e:
        return {"status": "error", "error": str(e), "vault_root": "", "node_count": 0}


@app.get("/api/nodes/recent")
def nodes_recent(
    days: int = Query(30),
    limit: int = Query(20),
    state: str = Query("active"),
):
    vr = _vault_root()
    graph.get(vr)
    return graph.recent(days=days, limit=limit, state=state)


@app.get("/api/nodes")
def nodes_list(
    node_type: str = Query(None, alias="type"),
    tag: str = Query(None),
    state: str = Query("active"),
):
    vr = _vault_root()
    g = graph.get(vr)
    state_filter = None if state == "all" else state
    results = graph.find(node_type=node_type, tag=tag, state=state_filter)
    augmented = []
    for item in results:
        uid = item["uid"]
        attrs = g.nodes.get(uid, {})
        augmented.append({
            **item,
            "tags": attrs.get("tags", []),
            "domains": attrs.get("domains", []),
            "summary": attrs.get("summary", ""),
            "updated_at": attrs.get("updated_at", ""),
        })
    return augmented


@app.get("/api/nodes/{uid}/neighbors")
def node_neighbors(uid: str):
    vr = _vault_root()
    g = graph.get(vr)
    if not g.has_node(uid):
        raise HTTPException(status_code=404, detail=f"Node {uid!r} not found")
    return graph.neighbors(uid)


@app.get("/api/nodes/{uid}")
def node_get(uid: str):
    vr = _vault_root()
    graph.get(vr)
    try:
        raw = vault_api.get(uid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {uid!r} not found")
    parsed = _parse_file(raw)
    nbrs = graph.neighbors(uid)
    response: dict = {
        "uid": uid,
        "frontmatter": parsed["frontmatter"],
        "body": parsed["body"],
        "neighbors": nbrs,
    }
    if parsed["asset"]:
        response["asset"] = parsed["asset"]
    return response


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    state: str = Query("active"),
):
    vr = _vault_root()
    graph.get(vr)
    return graph.search(query=q, state=state)


@app.get("/api/graph")
def graph_data():
    vr = _vault_root()
    g = graph.get(vr)
    nodes = [
        {
            "uid": uid,
            "title": attrs.get("title", ""),
            "type": attrs.get("type", ""),
            "tags": attrs.get("tags", []),
            "domains": attrs.get("domains", []),
            "summary": attrs.get("summary", ""),
            "status": attrs.get("status", ""),
            "state": attrs.get("state", "active"),
        }
        for uid, attrs in g.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, "rel_type": data.get("rel_type", "")}
        for u, v, data in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}

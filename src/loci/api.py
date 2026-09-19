"""
api.py
Loci vault API — clean interface for saving, reading, and listing vault items.

Used by:
  mcp_server.py       — Claude Desktop (MCP tools)
  tools/         — CLI entry points

Internal implementation lives in tools/. This module is the public facade.
"""

import contextlib
import io
import re
import sys
from pathlib import Path
from typing import Optional

import yaml

from loci import skill_assembly
from loci.tools.uid_generator import generate_uid as _generate_uid
from loci.tools.vault_init import NOT_CONFIGURED_MESSAGE, load_config
from loci.tools.write_file import (
    write_item as _write_item,
    patch_item as _patch_item,
    check_duplicate as _check_duplicate,
)
from loci.tools.type_registry import get_registry
from loci.tools.relation_registry import get_relation_registry
from loci.tools.frontmatter import load_frontmatter
from loci.tools import nx_graph as graph
from loci.tools.vault_linter import lint_vault as _lint_vault
from loci.tools import asset_registry as ar
from loci.tools.resolvers.dispatcher import dispatch_resolve


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vault_root() -> Path:
    config = load_config()
    if not config:
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    return Path(config["vault_root"]).expanduser()


def _loci_root() -> Path:
    return _vault_root().parent


def _stage_root() -> Path:
    """Stage root is a sibling of vault root's parent — loci-stage/."""
    return _vault_root().parent / "loci-stage"


_UID_RE = re.compile(r"[0-9a-f]{8}")

# Canonical meta files, used to answer read_meta for vaults that were never seeded.
REFERENCES_DIR = Path(__file__).parent / "skills" / "references"


def _frontmatter_uid(p: Path):
    """Return the `uid` field from a node file's frontmatter, or None."""
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, _ = load_frontmatter(raw)
    return fm.get("uid") if fm else None


def _resolve_vault_path(path: str) -> Path:
    """
    Resolve a vault reference to a filesystem path.

    Accepts an absolute path, a path relative to vault_root, or an
    8-character hex UID (looked up in the graph index).
    Raises FileNotFoundError when the reference points at something that is
    not a node file, or when a UID cannot be resolved to a file.
    The returned path is not guaranteed to exist — callers still check.
    """
    p = Path(path)
    if not p.is_absolute():
        p = _vault_root() / path
    if p.is_file():
        return p
    if p.exists():
        # A directory (including vault_root itself for an empty path) would
        # otherwise pass the callers' exists() guard and blow up on read/unlink.
        raise FileNotFoundError(f"Vault path is not a file: {p}")

    uid = path.strip()
    if _UID_RE.fullmatch(uid):
        g = graph.get(_vault_root())
        node_path = g.nodes[uid].get("path") if g.has_node(uid) else None
        if not node_path:
            raise FileNotFoundError(f"Vault file not found for UID: {uid}")
        resolved = Path(node_path)
        # The graph's path cache only notices changes in vault_root and its
        # immediate subdirectories, so a move deeper in the tree can leave a
        # stale path pointing at a different node's file. Confirm the file
        # still carries this uid before a caller patches or deletes it.
        if resolved.is_file() and _frontmatter_uid(resolved) != uid:
            raise FileNotFoundError(
                f"Vault file for UID {uid} is stale: {resolved} holds a different node"
            )
        return resolved

    return p


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_uid() -> str:
    """Generate a random 8-character hex UID."""
    return _generate_uid()


def _refuse_duplicate(title: str, url: Optional[str], tool: str) -> Optional[dict]:
    """
    The duplicate gate shared by save and save_asset. Returns the refusal
    dict describing the existing node, or None when the save may proceed.
    """
    dup = _check_duplicate(_vault_root(), title, url)
    if not dup:
        return None
    return {
        "duplicate": True,
        "uid": _frontmatter_uid(dup),
        "path": str(dup),
        "name": dup.name,
        "message": (
            f"A similar item already exists: {dup.name}. Ask the user "
            f"whether to update it (patch_vault) or save a new item "
            f"anyway ({tool} with allow_duplicate=True)."
        ),
    }


def save(
    type: str,
    title: str,
    body: str,
    tags: list = None,
    domains: list = None,
    summary: str = None,
    author: str = "self",
    relations: list = None,
    references: list = None,
    extra_fields: dict = None,
    allow_duplicate: bool = False,
) -> dict:
    """
    Write a new item to the vault. Returns {uid, path, type, title}.

    Refuses when a likely duplicate already exists — same title, or the same
    `extra_fields.source_url` — and returns {duplicate: True, uid, path, name}
    for it instead of writing. Pass allow_duplicate=True once the user has
    chosen to save a second item anyway. The check lives here rather than in
    the skill so a save cannot skip it.

    Only source_url takes part in the URL check. `references` are pages the
    item cites, and citing a bookmarked page is not saving it twice.
    """
    source_url = (extra_fields or {}).get("source_url")
    if not allow_duplicate:
        # Validate the type first so a bad type is reported as such rather
        # than as a duplicate of whatever the title happens to resemble.
        registry = get_registry(_vault_root())
        if type not in registry.type_names():
            raise ValueError(
                f"Unknown type: {type!r}. Must be one of: {sorted(registry.type_names())}"
            )
        refusal = _refuse_duplicate(title, source_url, "write_vault")
        if refusal:
            return refusal

    # Redirect stdout to prevent write_item's print() calls from corrupting
    # the MCP stdio protocol (or cluttering non-interactive use)
    with contextlib.redirect_stdout(io.StringIO()):
        result = _write_item(
            type=type,
            title=title,
            body=body,
            tags=tags,
            domains=domains,
            summary=summary,
            author=author,
            relations=relations,
            references=references,
            extra_fields=extra_fields,
            skip_duplicate_check=True,
        )
    if result and "uid" in result:
        graph.index_node(
            result["uid"],
            type=type,
            title=title,
            tags=tags or [],
            domains=domains or [],
            summary=summary or "",
            state="active",
            source_url=str((extra_fields or {}).get("source_url") or ""),
            subtype=str((extra_fields or {}).get("subtype") or ""),
            path=result["path"],
        )
        graph.index_edges(result["uid"], relations or [])
    return result


def delete(path: str) -> dict:
    """
    Delete a vault item. Accepts an absolute path, a path relative to vault_root,
    or an 8-character hex UID.
    Returns {deleted: True, path: str} or raises FileNotFoundError.
    """
    p = _resolve_vault_path(path)
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")
    # Read uid before deleting so we can drop the node from the graph
    fm, _ = load_frontmatter(p.read_text(encoding="utf-8"))
    uid = fm.get("uid") if fm else None
    p.unlink()
    if uid:
        graph.drop_node(uid)
    return {"deleted": True, "path": str(p)}


def patch(path: str, updates: dict, body: str = None) -> dict:
    """
    Patch frontmatter fields in an existing vault item.
    `updates` is merged into the existing frontmatter; `updated_at` is always bumped.
    If `body` is provided, it replaces the existing body.
    Accepts an absolute path, a path relative to vault_root, or an
    8-character hex UID.
    Returns {uid, path, type, title}.
    """
    p = _resolve_vault_path(path)
    result = _patch_item(str(p), updates, body)
    if result.get("uid"):
        graph.index_node(
            result["uid"],
            type=result.get("type", ""),
            title=result.get("title", ""),
            tags=result.get("tags", []),
            domains=result.get("domains", []),
            summary=result.get("summary", ""),
            state=result.get("state", "active"),
            source_url=result.get("source_url", ""),
            subtype=result.get("subtype", ""),
            aliases=result.get("aliases", []),
            language=result.get("language", ""),
            path=str(p),
        )
        graph.index_edges(result["uid"], result.get("relations", []))
    return result


def check_duplicate(type: str, title: str, url: str = None) -> dict:
    """
    Check whether a similar vault item already exists.
    Returns {"duplicate": False} or {"duplicate": True, "path": str, "name": str}.
    """
    registry = get_registry(_vault_root())
    if type not in registry.type_names():
        raise ValueError(
            f"Unknown type: {type!r}. Must be one of: {sorted(registry.type_names())}"
        )
    dup = _check_duplicate(_vault_root(), title, url)
    if dup:
        return {"duplicate": True, "path": str(dup), "name": dup.name}
    return {"duplicate": False}


def get(path: str) -> str:
    """
    Read a vault file. Accepts an absolute path, a path relative to vault_root,
    or an 8-character hex UID.
    Raises FileNotFoundError if the file does not exist.
    When the node has has_asset: true, asset content is appended inline (text files
    under the size threshold) or as a path reference (binary/large files).
    """
    p = _resolve_vault_path(path)
    if not p.exists():
        raise FileNotFoundError(f"Vault file not found: {p}")

    text = p.read_text(encoding="utf-8")

    fm, _ = load_frontmatter(text)
    if fm:
        uid = fm.get("uid")
        has_asset = fm.get("has_asset")
        if uid and isinstance(has_asset, list) and has_asset:
            resolved = None
            last_err = None
            for variant in has_asset:
                if not isinstance(variant, dict):
                    continue
                for loc in variant.get("locations", []):
                    if not isinstance(loc, dict):
                        continue
                    try:
                        resolved = dispatch_resolve(loc, _loci_root())
                        break
                    except (FileNotFoundError, ValueError) as e:
                        last_err = e
                if resolved:
                    break
            if resolved:
                size = resolved["size_bytes"]
                mime = resolved["mime_type"]
                apath = resolved["path"]
                if size <= ar.SIZE_THRESHOLD_BYTES and mime.startswith("text/"):
                    content = Path(apath).read_text(encoding="utf-8", errors="replace")
                    text += (
                        f"\n\n---\nasset_path: {apath}\n"
                        f"asset_mime_type: {mime}\n"
                        f"asset_size_bytes: {size}\n---\n\n"
                        f"{content}"
                    )
                else:
                    text += (
                        f"\n\nasset_path: {apath}\n"
                        f"asset_mime_type: {mime}\n"
                        f"asset_size_bytes: {size}"
                    )
            else:
                err_msg = str(last_err) if last_err else "no locations defined"
                text += f"\n\nasset_content: null\nasset_error: {err_msg}"

    return text


def resolve_asset(uid: str, format: str = None) -> dict:
    """
    Resolve an asset UID to its file path and metadata.
    Returns {path, mime_type, format, size_bytes}.
    """
    vault_root = _vault_root()
    loci_root = _loci_root()

    g = graph.get(vault_root)
    if not g.has_node(uid):
        raise FileNotFoundError(f"No vault node for asset UID: {uid}")
    node_path = g.nodes[uid].get("path")
    if not node_path:
        raise FileNotFoundError(f"No file path in vault node: {uid}")

    text = Path(node_path).read_text(encoding="utf-8")
    fm, _ = load_frontmatter(text)
    if fm is None:
        raise FileNotFoundError(f"No valid frontmatter in vault node: {node_path}")
    has_asset = fm.get("has_asset")

    if not isinstance(has_asset, list) or not has_asset:
        raise FileNotFoundError(f"Node {uid} has no asset locations")

    if format:
        variant = next(
            (v for v in has_asset if isinstance(v, dict) and v.get("format") == format),
            None,
        )
        if variant is None:
            raise ValueError(f"No {format!r} format for asset {uid}")
    else:
        variant = next(
            (v for v in has_asset if isinstance(v, dict) and v.get("primary")),
            next((v for v in has_asset if isinstance(v, dict)), None),
        )
        if variant is None:
            raise FileNotFoundError(f"Node {uid} has no valid asset variants")

    failed = []
    for loc in variant.get("locations", []):
        if not isinstance(loc, dict):
            continue
        try:
            result = dispatch_resolve(loc, loci_root)
            return {
                "path": result["path"],
                "mime_type": result["mime_type"],
                "format": variant.get("format"),
                "size_bytes": result["size_bytes"],
            }
        except (FileNotFoundError, ValueError) as e:
            failed.append(str(e))

    raise FileNotFoundError(f"Asset {uid} not reachable. Tried: {failed}")


def find_unregistered_assets() -> list:
    """Return relative paths of files in assets/ with no vault node has_asset local location."""
    loci_root = _loci_root()
    vault_root = _vault_root()
    ad = loci_root / "assets"
    if not ad.exists():
        return []

    registered: set[str] = set()
    for vf in vault_root.glob("*.md"):
        try:
            fm, _ = load_frontmatter(vf.read_text(encoding="utf-8"))
            if fm is None:
                continue
            has_asset = fm.get("has_asset")
            if not isinstance(has_asset, list):
                continue
            for variant in has_asset:
                if not isinstance(variant, dict):
                    continue
                for loc in variant.get("locations", []):
                    if not isinstance(loc, dict) or loc.get("scheme") != "local":
                        continue
                    raw = loc.get("path", "")
                    if not raw:
                        continue
                    p = Path(raw)
                    if p.is_absolute():
                        try:
                            raw = str(p.relative_to(loci_root))
                        except ValueError:
                            pass
                    registered.add(raw)
        except Exception:
            continue

    return [
        f"assets/{f.name}"
        for f in sorted(ad.iterdir())
        if f.is_file()
        and not f.name.startswith(".")
        and f"assets/{f.name}" not in registered
    ]


def save_asset(
    format: str,
    mime_type: str,
    title: str,
    content: bytes = None,
    source_path: str = None,
    summary: str = None,
    tags: list = None,
    domains: list = None,
    relations: list = None,
    node_type: str = "document",
    subtype: str = None,
    author: str = None,
    published_at: str = None,
    language: str = None,
    allow_duplicate: bool = False,
) -> dict:
    """
    Save a new asset with its vault proxy node using the crash-safe write sequence.
    Returns {uid, asset_path, vault_path}.

    Refuses when a node with this title already exists, the same way save does,
    and returns {duplicate: True, uid, path, name} before anything touches
    disk. Pass allow_duplicate=True once the user has chosen to save a second
    copy anyway.

    Provide either content (bytes) or source_path — not both.

    Args:
        content: Raw file bytes.
        source_path: Absolute path to a file on disk; bytes are read here.
        node_type: Vault node type for the proxy node ('document' or 'asset').
        subtype: For asset nodes — subtype field (e.g. 'book').
        author: Author name (included in extra_fields for asset nodes).
        published_at: Publication date string.
        language: ISO 639-1 language code.
    """
    if content is None and source_path is None:
        raise ValueError("Provide either content or source_path.")
    if content is not None and source_path is not None:
        raise ValueError("Provide either content or source_path, not both.")
    if not allow_duplicate:
        refusal = _refuse_duplicate(title, None, "save_asset")
        if refusal:
            return refusal
    if content is None:
        if not Path(source_path).is_absolute():
            raise ValueError("source_path must be an absolute path.")
        content = Path(source_path).read_bytes()
    from loci.tools.write_file import free_filename

    uid = _generate_uid()
    loci_root = _loci_root()
    vault_root = _vault_root()

    asset_rel_path = f"assets/{uid}.{format}"
    asset_final = loci_root / asset_rel_path
    asset_tmp = ar.assets_dir(loci_root) / f".{uid}.{format}.tmp"

    # The same choice _write_item makes below. Under allow_duplicate the title's
    # plain filename is taken, and recovery decides whether the proxy node was
    # written by checking this path — recording the first node's file would
    # make it skip the write and leave the asset with no node.
    vault_path = vault_root / free_filename(vault_root, title)

    has_asset_list = [
        {
            "format": format,
            "mime_type": mime_type,
            "primary": True,
            "locations": [{"scheme": "local", "path": asset_rel_path}],
        }
    ]

    # A document without a stated subtype is a note. Decide once, so the file,
    # the graph index, and the recovery intent all say the same thing.
    effective_subtype = subtype or ("note" if node_type == "document" else "")

    # The proxy node's frontmatter is fixed here, before the intent is written,
    # so that crash recovery (mcp_server._write_vault_proxy) can write the very
    # same node rather than reconstruct it from a subset of the arguments.
    extra_fields: dict = {"uid": uid, "has_asset": has_asset_list, "status": "evergreen"}
    if effective_subtype:
        extra_fields["subtype"] = effective_subtype
    if node_type == "asset":
        extra_fields["storage"] = "digital"
    if author:
        extra_fields["author"] = author
    if published_at:
        extra_fields["published_at"] = published_at
    if language:
        extra_fields["language"] = language

    vault_node = {
        "type": node_type,
        "title": title,
        "summary": summary,
        "tags": tags or [],
        "domains": domains or [],
        "relations": relations or [],
        "has_asset": has_asset_list,
        "subtype": effective_subtype,
        "extra_fields": extra_fields,
    }

    ar.assets_dir(loci_root).mkdir(parents=True, exist_ok=True)
    ar.pending_dir(loci_root).mkdir(parents=True, exist_ok=True)

    # Step 1: Write intent file
    intent_path = ar.write_intent(
        loci_root, uid, format, mime_type,
        str(asset_tmp), asset_rel_path, str(vault_path), vault_node,
    )

    # Steps 2+3: Stage to tmp, rename to final (atomic)
    asset_tmp.write_bytes(content)
    asset_tmp.rename(asset_final)

    # Step 6: Write vault proxy node
    with contextlib.redirect_stdout(io.StringIO()):
        result = _write_item(
            type=node_type,
            title=title,
            body=f"# {title}\n",
            tags=tags,
            domains=domains,
            summary=summary,
            relations=relations,
            extra_fields=extra_fields,
            skip_duplicate_check=True,
        )
    if "errors" in result:
        raise ValueError("; ".join(result["errors"]))
    graph.index_node(
        uid,
        type=node_type,
        title=title,
        tags=tags or [],
        domains=domains or [],
        summary=summary or "",
        state="active",
        subtype=effective_subtype,
        path=result["path"],
    )
    graph.index_edges(uid, relations or [])

    # Step 7: Delete intent file
    intent_path.unlink()

    return {"uid": uid, "asset_path": str(asset_final), "vault_path": result["path"]}


# ---------------------------------------------------------------------------
# Inbox API
# ---------------------------------------------------------------------------

def scan_inbox() -> dict:
    """
    Scan loci-stage/, classify files, write .inbox-plan.yaml.
    Returns plan summary.
    """
    from loci.tools.inbox_scanner import scan_stage
    from loci.tools.inbox_plan import write_plan

    stage_root = _stage_root()
    vault_root = _vault_root()

    scan_result = scan_stage(stage_root)
    items = scan_result["items"]
    summary = scan_result["summary"]
    extraction_warnings = scan_result["extraction_warnings"]

    plan = write_plan(stage_root, vault_root, items)

    result = {
        "status": "pending",
        "total_files": summary["total_files"],
        "total_content": summary["total_content"],
        "runs_estimated": summary["runs_estimated"],
        "plan_path": str(stage_root / ".inbox-plan.yaml"),
    }
    if extraction_warnings:
        result["extraction_warnings"] = extraction_warnings
    return result


def get_inbox_plan() -> dict:
    """
    Return current plan dict, or {'status': 'no-plan'} if none exists.
    """
    from loci.tools.inbox_plan import read_plan, get_pending_batch

    stage_root = _stage_root()
    plan = read_plan(stage_root)
    if plan is None:
        return {"status": "no-plan"}

    budget = plan.get("budget_per_run", {})
    file_batch = get_pending_batch(plan, "file", budget.get("files", 50))
    content_batch = get_pending_batch(plan, "content", budget.get("content", 10))

    return {
        "status": plan.get("status"),
        "budget_per_run": budget,
        "progress": plan.get("progress"),
        "next_file_items": file_batch[:3],   # preview only
        "next_content_items": content_batch[:3],  # preview only
    }


def approve_inbox_plan() -> dict:
    """
    Set plan status to approved.
    Raises ValueError if no plan or already in-progress/done.
    """
    from loci.tools.inbox_plan import approve_plan

    stage_root = _stage_root()
    return approve_plan(stage_root)


def execute_inbox_file_batch() -> dict:
    """
    Process next file-category batch from approved plan.
    For each item: read file from staging, save as asset node, delete staging file,
    update plan item to done.

    An item whose title already exists in the vault is parked as `duplicate`
    (staging file kept, nothing written) unless the plan item carries
    `allow_duplicate: true`; the caller re-queues it with update_inbox_item.
    Returns {processed: [...], failed: [...], duplicates: [...], remaining: int}.
    """
    from loci.tools.inbox_plan import read_plan, get_pending_batch, update_item_status

    stage_root = _stage_root()
    vault_root = _vault_root()

    plan = read_plan(stage_root)
    if plan is None:
        raise ValueError("No plan file found. Run scan_inbox first.")
    if plan.get("status") not in ("approved", "in-progress"):
        raise ValueError(
            f"Plan is not approved. Current status: {plan.get('status')!r}. "
            "Call approve_inbox_plan() first."
        )

    budget = plan.get("budget_per_run", {}).get("files", 50)
    batch = get_pending_batch(plan, "file", budget)

    # Check if a "Library" topic node exists
    library_uid = None
    try:
        results = graph.search("Library")
        for node in results:
            if node.get("type") == "topic" and node.get("title", "").strip() == "Library":
                library_uid = node.get("uid")
                break
    except Exception:
        pass

    processed = []
    failed = []
    duplicates = []

    for item in batch:
        item_path = item.get("path", "")
        file_path = stage_root / item_path

        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Staging file not found: {file_path}")

            content = file_path.read_bytes()
            title = item.get("title", file_path.stem)

            tags = [item.get("subtype", "book")] if item.get("subtype") else ["book"]
            domains = ["personal-library"]

            relations = []
            if library_uid:
                relations = [{"uid": library_uid, "type": "belongs-to"}]

            # The plan does not run a duplicate check, so approving it is not
            # consent to a second copy. A refusal parks the item rather than
            # failing it, and the per-item flag is the "save anyway".
            result = save_asset(
                content=content,
                format=item["format"],
                mime_type=item["mime_type"],
                title=title,
                node_type="asset",
                subtype=item.get("subtype", "book"),
                author=item.get("author"),
                language=item.get("language"),
                tags=tags,
                domains=domains,
                relations=relations,
                allow_duplicate=bool(item.get("allow_duplicate")),
            )

            if result.get("duplicate"):
                existing = {"existing_uid": result["uid"], "existing_path": result["path"], "existing_name": result["name"]}
                update_item_status(stage_root, item_path, "duplicate", existing)
                duplicates.append({"path": item_path, "title": title, **existing})
                continue

            update_item_status(
                stage_root,
                item_path,
                "done",
                {"uid": result["uid"], "vault_path": result["vault_path"], "asset_path": result["asset_path"]},
            )
            # Delete staging file after plan is updated; if unlink fails the
            # item is already marked done so a retry won't re-process it.
            try:
                file_path.unlink()
            except OSError:
                pass
            processed.append({"path": item_path, "uid": result["uid"], "title": title})

        except Exception as e:
            try:
                update_item_status(stage_root, item_path, "failed", {"error": str(e)})
            except Exception:
                pass
            failed.append({"path": item_path, "error": str(e)})

    # Count remaining
    plan = read_plan(stage_root)
    remaining = plan["progress"]["files"]["pending"] if plan else 0

    return {"processed": processed, "failed": failed, "duplicates": duplicates, "remaining": remaining}


def get_inbox_content_batch() -> dict:
    """
    Return next content-category batch for Claude to process.
    Reads each file's content (text files only).
    Does NOT update plan status.
    Returns {items: [...], remaining: int}.
    """
    from loci.tools.inbox_plan import read_plan, get_pending_batch

    stage_root = _stage_root()

    plan = read_plan(stage_root)
    if plan is None:
        raise ValueError("No plan file found. Run scan_inbox first.")
    if plan.get("status") not in ("approved", "in-progress"):
        raise ValueError(
            f"Plan is not approved. Current status: {plan.get('status')!r}. "
            "Call approve_inbox_plan() first."
        )

    budget = plan.get("budget_per_run", {}).get("content", 10)
    batch = get_pending_batch(plan, "content", budget)

    items_with_content = []
    for item in batch:
        item_path = item.get("path", "")
        file_path = stage_root / item_path

        item_copy = dict(item)
        try:
            if file_path.exists():
                item_copy["content"] = file_path.read_text(encoding="utf-8", errors="replace")
            else:
                item_copy["content"] = None
                item_copy["content_error"] = f"File not found: {file_path}"
        except Exception as e:
            item_copy["content"] = None
            item_copy["content_error"] = str(e)

        items_with_content.append(item_copy)

    remaining = plan["progress"]["content"]["pending"]

    return {"items": items_with_content, "remaining": remaining}


def update_inbox_item(path: str, status: str, uid: str = None, allow_duplicate: bool = None) -> dict:
    """
    Update a plan item's status. Content items: after Claude processes one.
    File items parked as `duplicate`: status="skipped" drops the item;
    status="pending" with allow_duplicate=True re-queues it for the next file
    batch, which then saves a second copy.
    """
    from loci.tools.inbox_plan import update_item_status, read_plan

    stage_root = _stage_root()
    result_data = {"uid": uid} if uid else None
    update_item_status(stage_root, path, status, result_data, allow_duplicate=allow_duplicate)

    plan = read_plan(stage_root)
    return {
        "updated": True,
        "path": path,
        "status": status,
        "progress": plan.get("progress") if plan else None,
    }


def list_items(type: str = None) -> dict:
    """
    List items in the vault, optionally filtered by type.
    Reads frontmatter from each file to determine type.
    Returns {type_name: [filename, ...], ...}.
    """
    vault_root = _vault_root()
    result: dict = {}
    for path in sorted(vault_root.glob("*.md")):
        fm, _ = load_frontmatter(path.read_text(encoding="utf-8"))
        if fm is None:
            continue
        node_type = fm.get("type")
        if not node_type:
            continue
        if type and node_type != type:
            continue
        result.setdefault(node_type, []).append(path.name)
    return result


def _append_yaml_entry(path: Path, list_key: str, entry: dict) -> None:
    """Append an entry to a YAML list file, preserving the comment header.
    Assumes all leading comment/blank lines form the header; inline comments are not preserved."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            header_end = i + 1
        else:
            break
    header = "".join(lines[:header_end])
    data = yaml.safe_load(text) or {list_key: []}
    entries = list(data.get(list_key) or [])
    entries.append(entry)
    dumped = yaml.dump(
        {list_key: entries},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    path.write_text(header + dumped, encoding="utf-8")


def define_type(
    name: str,
    extends: str,
    description: str,
    fields: list[dict] = None,
) -> dict:
    """
    Validate and append a new user-defined type to ontology-user.yaml.
    Returns {"defined": True, "name": str, "extends": str} on success,
    or {"defined": False, "errors": [...]} on validation failure.
    """
    from loci.tools.type_registry import reset_registry
    vault_root = _vault_root()
    result = get_registry(vault_root).validate_user_type(name, extends, fields)
    if not result["valid"]:
        return {"defined": False, "errors": result["errors"]}

    user_path = vault_root / "meta" / "ontology-user.yaml"
    if not user_path.exists():
        raise FileNotFoundError(f"User ontology not found: {user_path}")

    entry: dict = {"name": name, "extends": extends, "description": description}
    if fields:
        field_list = [
            {k: v for k, v in {
                "name": f["name"],
                "type": f.get("type", "string"),
                "values": f.get("values"),
            }.items() if v is not None}
            for f in fields
        ]
        if field_list:
            entry["fields"] = {"optional": field_list}

    _append_yaml_entry(user_path, "types", entry)
    reset_registry()
    return {"defined": True, "name": name, "extends": extends}


def define_relation(
    name: str,
    description: str,
    group: str = "",
    inverse_of: str = None,
) -> dict:
    """
    Validate and append a new user-defined relation to relation-dictionary-user.yaml.
    Returns {"defined": True, "name": str, "warnings": [...]} on success,
    or {"defined": False, "errors": [...], "warnings": [...]} on failure.
    """
    from loci.tools.relation_registry import reset_relation_registry
    vault_root = _vault_root()
    result = get_relation_registry(vault_root).validate_user_relation(
        name, group=group, description=description, inverse_of=inverse_of
    )
    if not result["valid"]:
        return {"defined": False, "errors": result["errors"], "warnings": result["warnings"]}

    user_path = vault_root / "meta" / "relation-dictionary-user.yaml"
    if not user_path.exists():
        raise FileNotFoundError(f"User relation dictionary not found: {user_path}")

    entry: dict = {"name": name, "description": description}
    if group:
        entry["group"] = group
    if inverse_of:
        entry["inverse_of"] = inverse_of

    _append_yaml_entry(user_path, "relations", entry)
    reset_relation_registry()
    return {"defined": True, "name": name, "warnings": result["warnings"]}


def app_version() -> str:
    """
    The installed distribution's version.

    Read from package metadata rather than by parsing pyproject.toml: an
    installed Loci has no pyproject.toml next to it, and this is what
    /api/health reports to the UI. pyproject.toml is still the single source
    of truth — the build backend copies `version` into the metadata this reads.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("loci")
    except PackageNotFoundError:  # pragma: no cover — running from a bare tree
        return "unknown"


def read_meta(file: str) -> str:
    """
    Read a vault meta file.
    file: type-dictionary | type-decision | tag-dictionary | field-dictionary |
          relation-dictionary | relation-dictionary-user | foreign-definitions |
          ontology | ontology-user | scheme-dictionary | scheme-dictionary-user |
          ontology-guide | has-asset-guide | update-workflow | config
    """
    if file == "config":
        cfg = load_config() or {}
        return f"app_version: {app_version()}\nvault_root: {cfg.get('vault_root', '')}\n"

    vault_root = _vault_root()
    file_map = {
        "type-dictionary":           vault_root / "meta" / "type-dictionary.md",
        "type-decision":             vault_root / "meta" / "type-decision.md",
        "tag-dictionary":            vault_root / "meta" / "tag-dictionary.md",
        "field-dictionary":          vault_root / "meta" / "field-dictionary.md",
        "relation-dictionary":       vault_root / "meta" / "relation-dictionary.yaml",
        "relation-dictionary-user":  vault_root / "meta" / "relation-dictionary-user.yaml",
        "foreign-definitions":       vault_root / "meta" / "foreign-definitions.md",
        "ontology":                  vault_root / "meta" / "ontology.yaml",
        "ontology-user":             vault_root / "meta" / "ontology-user.yaml",
        "scheme-dictionary":         vault_root / "meta" / "scheme-dictionary.yaml",
        "scheme-dictionary-user":    vault_root / "meta" / "scheme-dictionary-user.yaml",
        "ontology-guide":            vault_root / "meta" / "ontology-guide.md",
        "has-asset-guide":           vault_root / "meta" / "has-asset-guide.md",
        "update-workflow":           vault_root / "meta" / "update-workflow.md",
    }
    p = file_map.get(file)
    if not p:
        raise ValueError(f"Unknown meta file: {file!r}")
    if not p.exists():
        # Vaults that were never seeded fall back to the canonical copy in
        # references/ — every meta file keeps its basename there, so this
        # covers each key in file_map and any key added to it later. This is
        # the same fallback the registries apply when loading their YAML, so
        # what the model reads matches what write/lint validate against.
        fallback = REFERENCES_DIR / p.name
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Meta file not found: {p}")
    return p.read_text(encoding="utf-8")


def fetch_url_metadata(url: str) -> dict:
    """
    Lightly fetch a URL and extract title, site name, and description.
    Used for bookmark saves — does not return full page content.
    Returns {url, title, site_name, description} or adds an "error" key on failure.
    """
    import httpx
    from html.parser import HTMLParser

    class _MetaParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = None
            self.site_name = None
            self.description = None
            self._in_title = False

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "title":
                self._in_title = True
            elif tag == "meta":
                name = attrs.get("name", "").lower()
                prop = attrs.get("property", "").lower()
                content = attrs.get("content", "")
                if prop == "og:title" and not self.title:
                    self.title = content
                elif prop == "og:site_name":
                    self.site_name = content
                elif prop == "og:description" and not self.description:
                    self.description = content
                elif name == "description" and not self.description:
                    self.description = content

        def handle_data(self, data):
            if self._in_title and not self.title:
                self.title = data.strip()

        def handle_endtag(self, tag):
            if tag == "title":
                self._in_title = False

    try:
        response = httpx.get(url, follow_redirects=True, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; Loci/1.0)"})
        response.raise_for_status()
        parser = _MetaParser()
        parser.feed(response.text)
        return {
            "url": url,
            "title": parser.title or url,
            "site_name": parser.site_name,
            "description": parser.description,
        }
    except Exception as e:
        return {"url": url, "title": url, "site_name": None, "description": None, "error": str(e)}


def scan_directory(path: str, recursive: bool = False) -> dict:
    """
    Scan a directory for files and identify which already have vault nodes
    with a has_asset local location pointing to them.
    Returns {directory, total_files, unregistered: [...], registered: [...]}.
    """
    from loci.tools.directory_scanner import scan_directory as _scan_directory
    return _scan_directory(path, _vault_root(), recursive)


def read_skill(skill: str = "loci-save") -> str:
    """
    The assembled skill: packaged procedure plus the user's additions from
    vault/meta/<skill>-user.md. Works with no vault configured — the packaged
    half is what tells the model to ask for one — and says so in place of the
    additions.
    """
    try:
        vault_root = _vault_root()
    except RuntimeError:
        vault_root = None
    return skill_assembly.assemble(skill, vault_root)


def validate_type(name: str, extends: str, fields: list[dict] = None) -> dict:
    """
    Validate a proposed user type definition without writing anything.
    Returns {"valid": bool, "errors": [...], "resolved_fields": {...}}.
    """
    return get_registry(_vault_root()).validate_user_type(name, extends, fields)


def lint_vault() -> dict:
    """
    Run the vault linter over all vault files.
    Returns {"errors": [...], "warnings": [...], "stats": {...}}.
    """
    return _lint_vault(_vault_root())


def write_skill(content: str, skill: str = "loci-save", append: bool = False) -> str:
    """
    Write the user's additions for a skill — vault/meta/<skill>-user.md, the
    file read_skill appends to the packaged procedure. Returns the path written.

    Only that file. The packaged procedure ships inside the wheel and is
    replaced on upgrade, so an edit there was lost on the next install; the
    overlay lives in the vault, which is the user's, and is never reseeded.
    """
    p = skill_assembly.write_overlay(_vault_root(), skill, content, append=append)
    return str(p)


def write_meta(file: str, content: str) -> str:
    """
    Overwrite a vault meta file. Returns the path written.
    file: tag-dictionary | foreign-definitions | ontology-user
    (type-dictionary, ontology, and config are read-only via this API)
    """
    vault_root = _vault_root()
    file_map = {
        "tag-dictionary":      vault_root / "meta" / "tag-dictionary.md",
        "foreign-definitions": vault_root / "meta" / "foreign-definitions.md",
        "ontology-user":       vault_root / "meta" / "ontology-user.yaml",
    }
    p = file_map.get(file)
    if not p:
        raise ValueError(
            f"Unknown or read-only meta file: {file!r}. "
            f"Writable files: tag-dictionary, foreign-definitions, ontology-user"
        )
    # read_meta falls back to references/ for a vault that was never seeded, so
    # the model can reach this call with no meta/ directory on disk. Create it
    # rather than failing the write with a bare FileNotFoundError.
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)

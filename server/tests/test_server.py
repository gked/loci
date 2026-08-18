"""
tests/test_server.py
Tests for loci_mcp/server.py: tool error-wrapping and auth middleware.

Server tool functions are called directly as Python callables. The MCP
@mcp.tool() decorator registers them but preserves the original signature.

Startup side-effects in server.py (check_meta_version, recover_pending) are
wrapped in try/except, so importing the module is safe even without a
configured vault.
"""

import asyncio
import os
import threading
import pytest
from unittest.mock import patch

import loci_mcp.server as server
from loci_mcp.server import (
    generate_uid,
    check_duplicate,
    write_vault,
    list_vault,
    fetch_url_metadata,
    query_neighbors,
    query_related,
    query_path,
    query_recent,
    query_insights,
    find_nodes,
    search_vault,
    find_unregistered_assets,
    delete_vault,
    patch_vault,
    read_vault,
    read_meta,
    resolve_asset,
    write_meta,
    read_skill,
    write_skill,
    save_asset,
    _make_auth_app,
)


# ---------------------------------------------------------------------------
# Error-wrapping: FileNotFoundError → {"error": ...}
# ---------------------------------------------------------------------------

def test_delete_vault_wraps_file_not_found(tmp_vault):
    with patch("loci_mcp.server.loci.delete", side_effect=FileNotFoundError("not found")):
        result = delete_vault("/some/path.md")
    assert result == {"error": "not found"}


def test_patch_vault_wraps_file_not_found(tmp_vault):
    with patch("loci_mcp.server.loci.patch", side_effect=FileNotFoundError("missing")):
        result = patch_vault("/some/path.md", {"title": "X"})
    assert result == {"error": "missing"}


def test_patch_vault_wraps_value_error(tmp_vault):
    with patch("loci_mcp.server.loci.patch", side_effect=ValueError("bad field")):
        result = patch_vault("/some/path.md", {"bad": "field"})
    assert result == {"error": "bad field"}


def test_resolve_asset_wraps_file_not_found(tmp_vault):
    with patch("loci_mcp.server.loci.resolve_asset", side_effect=FileNotFoundError("no asset")):
        result = resolve_asset("abc12345")
    assert result == {"error": "no asset"}


def test_resolve_asset_wraps_value_error(tmp_vault):
    with patch("loci_mcp.server.loci.resolve_asset", side_effect=ValueError("wrong format")):
        result = resolve_asset("abc12345", format="xyz")
    assert result == {"error": "wrong format"}


def test_save_asset_wraps_any_exception(tmp_vault):
    with patch("loci_mcp.server.loci.save_asset", side_effect=RuntimeError("disk full")):
        result = save_asset(
            content="data", format="html", mime_type="text/html", title="Test"
        )
    assert result == {"error": "disk full"}


# ---------------------------------------------------------------------------
# Error-wrapping: returns error string (not dict)
# ---------------------------------------------------------------------------

def test_read_vault_returns_error_string_on_missing_file(tmp_vault):
    with patch("loci_mcp.server.loci.get", side_effect=FileNotFoundError("no file")):
        result = read_vault("/ghost.md")
    assert isinstance(result, str)
    assert "no file" in result


def test_read_meta_returns_error_string_on_unknown_key(tmp_vault):
    with patch("loci_mcp.server.loci.read_meta", side_effect=ValueError("Unknown meta file")):
        result = read_meta("bad-key")
    assert isinstance(result, str)
    assert "Unknown meta file" in result


def test_write_meta_returns_error_string_on_readonly(tmp_vault):
    with patch("loci_mcp.server.loci.write_meta", side_effect=ValueError("read-only")):
        result = write_meta("type-dictionary", "content")
    assert isinstance(result, str)
    assert "read-only" in result


def test_read_skill_returns_error_string_when_missing(tmp_vault):
    with patch("loci_mcp.server.loci.read_skill", side_effect=FileNotFoundError("no skill")):
        result = read_skill()
    assert isinstance(result, str)
    assert "no skill" in result


def test_write_skill_returns_error_string_when_missing(tmp_vault):
    with patch("loci_mcp.server.loci.write_skill", side_effect=FileNotFoundError("no skill")):
        result = write_skill("content")
    assert isinstance(result, str)
    assert "no skill" in result


# ---------------------------------------------------------------------------
# _make_auth_app
# ---------------------------------------------------------------------------

async def _call_middleware(middleware, scope):
    """Run the middleware and collect all sent messages."""
    messages = []

    async def send(msg):
        messages.append(msg)

    await middleware(scope, None, send)
    return messages


def _run_async(coro):
    """
    Run a coroutine to completion on a dedicated thread.

    Not `asyncio.run()`: Playwright's sync API (server/tests/e2e/) keeps an
    event loop alive in the main thread for the whole session, and both
    `asyncio.run()` and `loop.run_until_complete()` refuse to start while
    another loop is running there. Running on our own thread makes these tests
    independent of whether the e2e suite is part of the same pytest process.
    """
    box = {}

    def target():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as e:  # re-raised on the calling thread below
            box["error"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()

    if "error" in box:
        raise box["error"]
    return box["value"]


def test_make_auth_app_no_token_returns_original_app(monkeypatch):
    monkeypatch.delenv("LOCI_TOKEN", raising=False)

    async def dummy(scope, receive, send):
        pass

    wrapped = _make_auth_app(dummy)
    assert wrapped is dummy


def test_make_auth_app_empty_token_returns_original_app(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "")

    async def dummy(scope, receive, send):
        pass

    wrapped = _make_auth_app(dummy)
    assert wrapped is dummy


def test_auth_middleware_allows_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "secret123")

    allowed = []

    async def dummy(scope, receive, send):
        allowed.append(True)

    middleware = _make_auth_app(dummy)

    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer secret123")],
        "query_string": b"",
    }
    _run_async(_call_middleware(middleware, scope))
    assert allowed == [True]


def test_auth_middleware_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "secret123")

    async def dummy(scope, receive, send):
        pass

    middleware = _make_auth_app(dummy)

    scope = {
        "type": "http",
        "headers": [],
        "query_string": b"",
    }
    messages = _run_async(_call_middleware(middleware, scope))
    assert messages[0]["status"] == 401
    assert messages[1]["body"] == b"Unauthorized"


def test_auth_middleware_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "secret123")

    async def dummy(scope, receive, send):
        pass

    middleware = _make_auth_app(dummy)

    scope = {
        "type": "http",
        "headers": [(b"authorization", b"Bearer wrongtoken")],
        "query_string": b"",
    }
    messages = _run_async(_call_middleware(middleware, scope))
    assert messages[0]["status"] == 401


def test_auth_middleware_allows_token_as_query_param(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "secret123")

    allowed = []

    async def dummy(scope, receive, send):
        allowed.append(True)

    middleware = _make_auth_app(dummy)

    scope = {
        "type": "http",
        "headers": [],
        "query_string": b"token=secret123",
    }
    _run_async(_call_middleware(middleware, scope))
    assert allowed == [True]


def test_auth_middleware_passes_through_non_http_scope(monkeypatch):
    monkeypatch.setenv("LOCI_TOKEN", "secret123")

    passed = []

    async def dummy(scope, receive, send):
        passed.append(scope["type"])

    middleware = _make_auth_app(dummy)

    scope = {"type": "lifespan"}
    _run_async(_call_middleware(middleware, scope))
    assert passed == ["lifespan"]


# ---------------------------------------------------------------------------
# Tool functions — happy-path coverage
# ---------------------------------------------------------------------------

def test_generate_uid_delegates_to_api(tmp_vault):
    with patch("loci_mcp.server.loci.generate_uid", return_value="abc12345"):
        result = generate_uid()
    assert result == "abc12345"


def test_check_duplicate_returns_no_duplicate(tmp_vault):
    with patch("loci_mcp.server.loci.check_duplicate", return_value={"duplicate": False}):
        result = check_duplicate("document", "Some Title")
    assert result == {"duplicate": False}


def test_write_vault_returns_uid(tmp_vault):
    payload = {"uid": "abc12345", "path": "/p/doc.md", "type": "document", "title": "T"}
    with patch("loci_mcp.server.loci.save", return_value=payload):
        result = write_vault("document", "T", "body")
    assert result["uid"] == "abc12345"


def test_patch_vault_accepts_uid_as_path(tmp_vault):
    """No search_vault round-trip needed: the UID resolves on its own."""
    written = write_vault("document", "Patch By UID", "body", extra_fields={"status": "draft"})
    result = patch_vault(written["uid"], {"status": "done"})
    assert result["uid"] == written["uid"]
    assert "error" not in result
    assert "status: done" in read_vault(written["uid"])


def test_patch_vault_unknown_uid_returns_error(tmp_vault):
    result = patch_vault("deadbeef", {"status": "done"})
    assert "deadbeef" in result["error"]


def test_delete_vault_directory_returns_error(tmp_vault):
    """A directory must come back as an error dict, not an uncaught IsADirectoryError."""
    (tmp_vault / "adir").mkdir(exist_ok=True)
    result = delete_vault("adir")
    assert "not a file" in result["error"]
    assert (tmp_vault / "adir").is_dir()


def test_list_vault_includes_startup_notice_once(tmp_vault, monkeypatch):
    monkeypatch.setattr(server, "_startup_notice", "meta updated to v3")
    monkeypatch.setattr(server, "_first_ready_work_done", True)
    with patch("loci_mcp.server.loci.list_items", return_value={}):
        result = list_vault()
    assert "meta updated to v3" in result["_notice"]
    assert server._startup_notice is None  # cleared after first show


def test_tool_call_survives_meta_setup_failure(tmp_vault, monkeypatch):
    """Seeding writes to the vault. A read-only mount, or one owned by another
    uid, must leave the tool working off the reference copies — not failing."""
    monkeypatch.setattr(server, "_startup_notice", None)
    monkeypatch.setattr(server, "_first_ready_work_done", True)

    def boom():
        raise PermissionError("Read-only file system: '/knowledge-vault/meta'")

    monkeypatch.setattr(server, "ensure_ready", boom)
    with patch("loci_mcp.server.loci.list_items", return_value={"notes": []}):
        result = list_vault()

    assert result["notes"] == []          # the tool still answered
    assert "Read-only file system" in result["_notice"]


def test_fetch_url_metadata_returns_dict(tmp_vault):
    expected = {"url": "https://example.com", "title": "Example", "site_name": None, "description": None}
    with patch("loci_mcp.server.loci.fetch_url_metadata", return_value=expected):
        result = fetch_url_metadata("https://example.com")
    assert result["title"] == "Example"


def test_query_neighbors_returns_list(tmp_vault):
    neighbors = [{"uid": "n002", "title": "Beta", "type": "task", "rel_type": "relates-to", "direction": "out"}]
    with patch("loci_mcp.server.graph.get"), \
         patch("loci_mcp.server.graph.neighbors", return_value=neighbors):
        result = query_neighbors("n001")
    assert len(result) == 1
    assert result[0]["uid"] == "n002"


def test_query_related_returns_list(tmp_vault):
    related = [{"uid": "n002", "title": "Beta", "type": "task", "distance": 1, "summary": ""}]
    with patch("loci_mcp.server.graph.get"), \
         patch("loci_mcp.server.graph.related", return_value=related):
        result = query_related("n001")
    assert result[0]["distance"] == 1


def test_query_path_returns_path(tmp_vault):
    nodes = [
        {"uid": "n001", "title": "Alpha", "type": "document"},
        {"uid": "n002", "title": "Beta",  "type": "task"},
    ]
    with patch("loci_mcp.server.graph.get"), \
         patch("loci_mcp.server.graph.path", return_value=nodes):
        result = query_path("n001", "n002")
    assert len(result) == 2
    assert result[-1]["uid"] == "n002"


def test_find_nodes_returns_matching_list(tmp_vault):
    found = [{"uid": "n001", "title": "Alpha", "type": "task", "path": "/p", "status": "open", "due_date": "", "language": ""}]
    with patch("loci_mcp.server.graph.get"), \
         patch("loci_mcp.server.graph.find", return_value=found):
        result = find_nodes(type="task")
    assert result[0]["type"] == "task"


def test_search_vault_returns_results(tmp_vault):
    hits = [{"uid": "n001", "title": "Alpha", "type": "document", "path": "/p", "summary": ""}]
    with patch("loci_mcp.server.graph.get"), \
         patch("loci_mcp.server.graph.search", return_value=hits):
        result = search_vault("alpha")
    assert result[0]["uid"] == "n001"


def test_query_recent_returns_list(tmp_vault):
    nodes = [{"uid": "r001", "title": "Fresh", "type": "task", "path": "/p", "updated_at": "2026-04-20T00:00:00Z", "status": "todo"}]
    with patch("loci_mcp.server.graph.get") as mock_get, \
         patch("loci_mcp.server.graph.recent", return_value=nodes):
        result = query_recent(days=30)
    mock_get.assert_called_once()
    assert result[0]["uid"] == "r001"
    assert result[0]["updated_at"] == "2026-04-20T00:00:00Z"


def test_query_insights_returns_list(tmp_vault):
    nodes = [{"uid": "i001", "title": "Bridge", "type": "document", "domains": ["technology-engineering"],
              "connects_to_domains": ["personal-development"], "degree": 3}]
    with patch("loci_mcp.server.graph.get") as mock_get, \
         patch("loci_mcp.server.graph.insights", return_value=nodes):
        result = query_insights()
    mock_get.assert_called_once()
    assert result[0]["uid"] == "i001"
    assert "personal-development" in result[0]["connects_to_domains"]


def test_find_unregistered_assets_returns_list(tmp_vault):
    with patch("loci_mcp.server.loci.find_unregistered_assets", return_value=["assets/orphan.pdf"]):
        result = find_unregistered_assets()
    assert "assets/orphan.pdf" in result

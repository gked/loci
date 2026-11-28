"""
tests/test_save_review.py
The save review: `propose_save` builds a draft without writing it, and the MCP
App view (`ui://loci/node-view.html`) is what turns it into a Save button.

The draft check is advisory. `write_vault` stays the authority — it runs the
same gates when the user clicks Save — so these tests pin two things: that a
draft never touches the vault, and that every problem `write_vault` would
refuse the draft for is reported here first, so the user sees it before the
click rather than after.
"""
import asyncio
import re
import threading
from types import SimpleNamespace

import pytest

from loci import api, mcp_server as server
from loci.mcp_apps import NODE_VIEW_URI, UI_MIME, node_view_html

GOOD = dict(
    type="document",
    title="Save review draft",
    body="# Heading\n\nSome **body** text.\n",
    tags=["draft-tag"],
    summary="A draft used to test the save review.",
    extra_fields={"subtype": "note", "status": "evergreen"},
)


def _vault_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# api.propose_save
# ---------------------------------------------------------------------------

def test_a_draft_writes_nothing(tmp_vault):
    before = _vault_files(tmp_vault)
    result = api.propose_save(**GOOD)
    assert result["errors"] == []
    assert _vault_files(tmp_vault) == before


def test_a_draft_echoes_every_field_so_save_can_send_them_back(tmp_vault):
    draft = api.propose_save(
        **GOOD, domains=["technology-engineering"], author="self",
        references=[{"url": "https://example.com", "title": "Ex", "source_type": "article"}],
    )["draft"]
    assert draft["type"] == "document"
    assert draft["title"] == GOOD["title"]
    assert draft["body"] == GOOD["body"]
    assert draft["tags"] == ["draft-tag"]
    assert draft["domains"] == ["technology-engineering"]
    assert draft["summary"] == GOOD["summary"]
    assert draft["author"] == "self"
    assert draft["extra_fields"] == GOOD["extra_fields"]
    assert draft["references"][0]["url"] == "https://example.com"


def test_the_draft_has_no_uid_because_none_exists_until_it_is_saved(tmp_vault):
    result = api.propose_save(**GOOD)
    assert "uid" not in result["draft"]
    assert "uid" not in result


def test_relations_arrive_with_the_title_of_what_they_point_at(tmp_vault):
    result = api.propose_save(**GOOD, relations=[{"uid": "hub00001", "type": "about"}])
    assert result["errors"] == []
    rel = result["relations"][0]
    assert (rel["uid"], rel["type"]) == ("hub00001", "about")
    assert rel["title"] == "Central Hub Topic"
    assert rel["node_type"] == "topic"
    assert rel["missing"] is False


def test_a_relation_to_a_node_that_is_not_there_is_flagged_not_hidden(tmp_vault):
    rel = api.propose_save(**GOOD, relations=[{"uid": "deadbeef", "type": "about"}])["relations"][0]
    assert rel["missing"] is True
    assert rel["title"] is None


def test_an_unknown_relation_type_is_an_error(tmp_vault):
    result = api.propose_save(**GOOD, relations=[{"uid": "hub00001", "type": "no-such-relation"}])
    assert any("no-such-relation" in e for e in result["errors"])


def test_an_unknown_type_is_reported_as_an_error_not_raised(tmp_vault):
    result = api.propose_save(**{**GOOD, "type": "no-such-type"})
    assert any("no-such-type" in e for e in result["errors"])


def test_a_missing_required_field_is_reported(tmp_vault):
    result = api.propose_save(**{**GOOD, "extra_fields": {}})
    assert any("subtype" in e for e in result["errors"])


def test_an_enum_value_outside_its_set_is_reported(tmp_vault):
    result = api.propose_save(**{**GOOD, "extra_fields": {"subtype": "not-a-subtype", "status": "evergreen"}})
    assert any("not-a-subtype" in e for e in result["errors"])


def test_an_empty_title_is_an_error(tmp_vault):
    assert api.propose_save(**{**GOOD, "title": "  "})["errors"]


def test_a_duplicate_title_is_reported_with_the_existing_node(tmp_vault):
    result = api.propose_save(**{**GOOD, "title": "Central Hub Topic"})
    dup = result["duplicate"]
    assert dup["uid"] == "hub00001"
    assert result["errors"] == []          # a duplicate is a choice, not a failure


def test_no_duplicate_is_none(tmp_vault):
    assert api.propose_save(**GOOD)["duplicate"] is None


def test_a_draft_that_save_would_accept_is_accepted_by_save(tmp_vault):
    """The two gates must agree: a clean draft saves, with the same fields."""
    result = api.propose_save(**GOOD)
    assert result["errors"] == []
    saved = api.save(**result["draft"])
    assert saved.get("uid")
    assert "errors" not in saved and not saved.get("duplicate")


@pytest.mark.parametrize("override", [
    {"type": "no-such-type"},
    {"extra_fields": {}},
    {"extra_fields": {"subtype": "nope", "status": "evergreen"}},
    {"relations": [{"uid": "hub00001", "type": "no-such-relation"}]},
])
def test_whatever_save_refuses_the_draft_check_reports_first(tmp_vault, override):
    fields = {**GOOD, **override}
    errors = api.propose_save(**fields)["errors"]
    try:
        refused = api.save(**fields).get("errors") or []
    except ValueError as exc:
        refused = [str(exc)]
    assert refused, "test setup: save should refuse this draft"
    assert errors, "propose_save accepted a draft that save refuses"


# ---------------------------------------------------------------------------
# the MCP tool
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run a coroutine to completion on its own thread. Not asyncio.run() here: under the e2e
    suite Playwright's sync API keeps a loop alive on the main thread for the whole session,
    and asyncio.run() refuses to start beside it (see tests/test_server.py)."""
    box = {}

    def target():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:      # re-raised on the calling thread
            box["error"] = exc

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def _tools():
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_propose_save_is_a_tool_with_the_node_view_attached():
    tool = _tools()["propose_save"]
    assert tool.meta["ui"]["resourceUri"] == NODE_VIEW_URI


def test_propose_save_is_guarded_like_every_tool_that_touches_the_vault():
    fn = server.mcp._tool_manager.get_tool("propose_save").fn
    assert getattr(fn, "__loci_guarded__", False)


def test_write_vault_does_not_carry_the_view():
    """Only the draft shows the card. A direct write_vault must not open one."""
    assert not (_tools()["write_vault"].meta or {}).get("ui")


def _ctx(extensions):
    caps = SimpleNamespace(model_extra={"extensions": extensions} if extensions is not None else {})
    return SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(capabilities=caps)))


def test_client_support_needs_the_extension_and_the_mime_type():
    ok = {"io.modelcontextprotocol/ui": {"mimeTypes": [UI_MIME]}}
    assert server._client_supports_apps(_ctx(ok)) is True
    assert server._client_supports_apps(_ctx(None)) is False
    assert server._client_supports_apps(_ctx({})) is False
    assert server._client_supports_apps(_ctx({"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html"]}})) is False
    assert server._client_supports_apps(_ctx({"io.modelcontextprotocol/ui": {}})) is False


def test_client_support_is_false_when_the_session_cannot_be_read():
    assert server._client_supports_apps(None) is False
    assert server._client_supports_apps(SimpleNamespace()) is False
    assert server._client_supports_apps(SimpleNamespace(session=SimpleNamespace(client_params=None))) is False


def _call(name, args):
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def run():
        async with connect(server.mcp._mcp_server) as client:
            return await client.call_tool(name, args)
    return _run_async(run())


def _review_seen_by(extensions):
    """`review` as a client sees it after a real initialize handshake declaring `extensions`.

    The other tests fake the request context; this is the one that proves the whole chain: the
    declaration crosses the wire, FastMCP hands the tool its Context, and the tool reads it."""
    import anyio
    import mcp.types as types
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    async def run():
        out = []
        srv = server.mcp._mcp_server
        async with create_client_server_memory_streams() as (c, s):
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: srv.run(s[0], s[1], srv.create_initialization_options()))
                async with ClientSession(c[0], c[1]) as session:
                    caps = types.ClientCapabilities.model_validate({"extensions": extensions} if extensions else {})
                    await session.send_request(types.ClientRequest(types.InitializeRequest(
                        params=types.InitializeRequestParams(
                            protocolVersion=types.LATEST_PROTOCOL_VERSION, capabilities=caps,
                            clientInfo=types.Implementation(name="probe", version="0")))), types.InitializeResult)
                    await session.send_notification(types.ClientNotification(types.InitializedNotification()))
                    out.append((await session.call_tool("propose_save", GOOD)).structuredContent["review"])
                    tg.cancel_scope.cancel()
        return out[0]
    return _run_async(run())


@pytest.mark.parametrize("extensions, expected", [
    ({"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}, "shown"),
    (None, "unsupported"),
    ({"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html"]}}, "unsupported"),
    ({"some.other/extension": {}}, "unsupported"),
])
def test_the_card_is_offered_only_to_a_client_that_declared_it_in_the_handshake(tmp_vault, extensions, expected):
    assert _review_seen_by(extensions) == expected


def test_a_host_that_cannot_render_is_told_to_confirm_in_chat(tmp_vault):
    """The in-memory client declares no UI extension, like Hermes or any text-only host."""
    result = _call("propose_save", GOOD)
    out = result.structuredContent
    assert out["review"] == "unsupported"
    assert "write_vault" in out["message"]
    assert out["draft"]["title"] == GOOD["title"]


def test_the_message_for_a_rendering_host_forbids_writing_around_the_button(tmp_vault, monkeypatch):
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: True)
    out = _call("propose_save", GOOD).structuredContent
    assert out["review"] == "shown"
    assert "do not call write_vault" in out["message"].lower()


def test_a_draft_with_errors_is_not_shown_as_ready(tmp_vault, monkeypatch):
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: True)
    out = _call("propose_save", {**GOOD, "extra_fields": {}}).structuredContent
    assert out["errors"]
    assert out["review"] == "shown"          # the user still sees the draft and the problems
    assert "fix" in out["message"].lower()


def test_propose_save_leaves_the_vault_as_it_found_it(tmp_vault):
    _call("list_vault", {})          # the first guarded call seeds meta/; that is not the draft's doing
    before = _vault_files(tmp_vault)
    _call("propose_save", GOOD)
    assert _vault_files(tmp_vault) == before


def test_a_tag_that_repeats_the_type_is_warned_about_before_the_save(tmp_vault):
    result = api.propose_save(**{**GOOD, "tags": ["document"]})
    assert result["tag_warnings"]
    assert "tag_warnings" not in api.propose_save(**GOOD)


# ---------------------------------------------------------------------------
# the view resource
# ---------------------------------------------------------------------------

def test_the_view_is_served_as_an_mcp_app_resource():
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def run():
        async with connect(server.mcp._mcp_server) as client:
            return await client.read_resource(NODE_VIEW_URI)
    content = _run_async(run()).contents[0]
    assert content.mimeType == UI_MIME == "text/html;profile=mcp-app"
    assert content.text == node_view_html()
    assert "<!doctype html>" in content.text.lower()


def test_the_view_ships_inside_the_package():
    """It is read at runtime, so it must live under src/loci/ to reach the wheel."""
    from pathlib import Path
    import loci
    assert Path(loci.__file__).parent in Path(__import__("loci.mcp_apps", fromlist=["x"]).__file__).parents
    assert len(node_view_html()) > 2000


def test_the_view_makes_no_network_requests():
    """The host's default CSP blocks them; a view that needs one is broken in Claude."""
    html = node_view_html()
    for needle in ("http://", "https://", "fetch(", "XMLHttpRequest", "WebSocket", "<script src", "@import"):
        assert needle not in html, needle


# ---------------------------------------------------------------------------
# found in review: each of these was a defect or an unpinned behaviour
# ---------------------------------------------------------------------------

def test_the_draft_leaves_out_what_is_unset_so_it_validates_against_write_vault(tmp_vault):
    """write_vault declares `summary: str = None`; an explicit null fails its schema, so a
    draft with no summary used to be rejected on the way back."""
    draft = api.propose_save(type="document", title="No summary", body="b",
                             extra_fields={"subtype": "note", "status": "evergreen"})["draft"]
    assert "summary" not in draft and "tags" not in draft and "relations" not in draft
    assert None not in draft.values()


@pytest.mark.parametrize("fields", [
    dict(type="document", title="Round trip, bare", body="b", extra_fields={"subtype": "note", "status": "evergreen"}),
    dict(GOOD, title="Round trip, full", domains=["technology-engineering"], author="alice",
         relations=[{"uid": "hub00001", "type": "about"}],
         references=[{"url": "https://example.com", "title": "Ex", "source_type": "article"}]),
])
def test_the_draft_goes_back_through_write_vault_unchanged(tmp_vault, fields):
    """The whole point of echoing it: through the MCP schema, not just the Python call."""
    draft = _call("propose_save", fields).structuredContent["draft"]
    written = _call("write_vault", draft)
    assert not written.isError, written.content
    assert json_of(written).get("uid")


def json_of(result):
    import json
    return result.structuredContent or json.loads(result.content[0].text)


def test_the_draft_echoes_a_custom_author(tmp_vault):
    assert api.propose_save(**GOOD, author="alice")["draft"]["author"] == "alice"


def test_a_check_that_raises_becomes_an_error_the_card_can_show(tmp_vault):
    result = api.propose_save(**{**GOOD, "extra_fields": {"subtype": ["a"], "status": "evergreen"}})
    assert result["errors"] and result["draft"]["title"] == GOOD["title"]


def test_a_malformed_uid_is_an_error(tmp_vault):
    r = api.propose_save(**{**GOOD, "extra_fields": {**GOOD["extra_fields"], "uid": "XYZ"}})
    assert any("not a valid uid" in e for e in r["errors"])


def test_a_taken_uid_is_an_error(tmp_vault):
    from loci.tools.frontmatter import load_frontmatter
    taken = next(
        str(fm["uid"]) for p in tmp_vault.glob("*.md")
        for fm in [load_frontmatter(p.read_text(encoding="utf-8"))[0] or {}]
        if re.fullmatch(r"[0-9a-f]{8}", str(fm.get("uid", "")))
    )
    r = api.propose_save(**{**GOOD, "extra_fields": {**GOOD["extra_fields"], "uid": taken}})
    assert any("already belongs" in e for e in r["errors"])


def test_has_asset_problems_are_reported_both_ways(tmp_vault):
    bad = api.propose_save(**{**GOOD, "extra_fields": {**GOOD["extra_fields"], "has_asset": [{"scheme": "nope", "path": "x"}]}})
    assert any("has_asset" in e for e in bad["errors"])
    soft = api.propose_save(**{**GOOD, "extra_fields": {**GOOD["extra_fields"], "has_asset": "nonsense://x"}})
    assert soft["errors"] == [] and any("has_asset" in w for w in soft["warnings"])


def test_body_inside_extra_fields_is_rerouted_like_write_item_does(tmp_vault):
    used = api.propose_save(**{**GOOD, "body": "", "extra_fields": {**GOOD["extra_fields"], "body": "from extra"}})
    assert used["draft"]["body"] == "from extra"
    assert "body" not in used["draft"]["extra_fields"]
    assert any("used as the body" in w for w in used["warnings"])
    kept = api.propose_save(**{**GOOD, "body": "argument", "extra_fields": {**GOOD["extra_fields"], "body": "extra"}})
    assert kept["draft"]["body"] == "argument" and "body" not in kept["draft"]["extra_fields"]
    assert any("argument won" in w for w in kept["warnings"])


def test_a_duplicate_source_url_is_reported_under_a_different_title(tmp_vault):
    first = api.save(type="bookmark", title="First bookmark", body="x",
                     extra_fields={"source_url": "https://example.com/a", "site_name": "ex", "subtype": "link"})
    assert first.get("uid"), first
    r = api.propose_save(type="bookmark", title="A different title", body="y",
                         extra_fields={"source_url": "https://example.com/a", "site_name": "ex", "subtype": "link"})
    assert r["duplicate"] and r["duplicate"]["uid"] == first["uid"]


def test_an_unknown_type_never_looks_up_a_duplicate(tmp_vault):
    r = api.propose_save(**{**GOOD, "type": "no-such-type", "title": "Central Hub Topic"})
    assert r["duplicate"] is None and r["errors"]


def test_an_unreadable_graph_does_not_call_relations_missing(tmp_vault, monkeypatch):
    def boom(root):
        raise RuntimeError("graph is broken")
    monkeypatch.setattr(api.graph, "get", boom)
    rel = api.propose_save(**GOOD, relations=[{"uid": "hub00001", "type": "about"}])["relations"][0]
    assert rel["missing"] is False and rel["title"] is None


def test_tag_advice_knows_the_subtype_and_the_relations(tmp_vault):
    assert api.propose_save(**{**GOOD, "tags": ["note"]})["tag_warnings"], "a tag repeating the subtype"
    bare = api.propose_save(**{**GOOD, "tags": ["central-hub-topic"]})["tag_warnings"][0]
    linked = api.propose_save(**{**GOOD, "tags": ["central-hub-topic"],
                                 "relations": [{"uid": "hub00001", "type": "about"}]})["tag_warnings"][0]
    assert "relation" in bare and "already links" in linked


def test_each_review_state_gets_its_own_instruction(tmp_vault, monkeypatch):
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: True)
    clean = _call("propose_save", GOOD).structuredContent
    dup = _call("propose_save", {**GOOD, "title": "Central Hub Topic"}).structuredContent
    bad = _call("propose_save", {**GOOD, "extra_fields": {}}).structuredContent
    assert clean["message"] == server._REVIEW_SHOWN
    assert dup["message"] == server._REVIEW_SHOWN_DUPLICATE and "do not ask about the duplicate" in dup["message"].lower()
    assert bad["message"] == server._REVIEW_SHOWN_WITH_ERRORS and "once more" in bad["message"]
    # the gate's own advice ("ask the user whether to update...") would send the model to ask again in chat
    assert dup["duplicate"]["uid"] == "hub00001" and "message" not in dup["duplicate"]
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: False)
    out = _call("propose_save", GOOD).structuredContent
    assert out["message"] == server._REVIEW_UNSUPPORTED and "do not call write_vault" not in out["message"].lower()


def test_the_tool_description_says_to_stop_when_the_card_is_shown():
    assert "do not call" in _tools()["propose_save"].description.lower()


def test_an_empty_summary_is_kept_because_save_would_store_it(tmp_vault):
    assert api.propose_save(**{**GOOD, "summary": ""})["draft"]["summary"] == ""


def test_a_relation_to_a_node_that_is_not_there_is_a_warning_the_model_sees(tmp_vault):
    out = api.propose_save(**GOOD, relations=[{"uid": "nosuchid", "type": "about"}])
    assert out["errors"] == [] and any("nosuchid" in w for w in out["warnings"])


def test_propose_save_is_marked_read_only_so_a_host_need_not_ask_per_call():
    assert _tools()["propose_save"].annotations.readOnlyHint is True


def test_the_messages_tell_the_model_what_to_say_about_a_stale_card_and_how_often_to_retry():
    assert "out of date" in server._REVIEW_SHOWN
    assert "at most once" in server._REVIEW_SHOWN_WITH_ERRORS and "never invent" in server._REVIEW_SHOWN_WITH_ERRORS
    assert "out of date" in server._REVIEW_SHOWN_WITH_ERRORS


def test_the_save_skill_tells_the_model_to_stop_at_the_card_and_what_to_do_after():
    text = api.read_skill("loci-save")
    step = text[text.index("loci__propose_save"):]
    for phrase in ('review: "shown"', "stop", "Never call `loci__write_vault` yourself", "read_vault", "feedback", "again", "unsupported", "once;", "out of date and not to click it", "went through after all"):
        assert phrase in step, phrase


def test_every_shown_message_that_can_be_followed_by_a_new_proposal_warns_about_the_old_card():
    for text in (server._REVIEW_SHOWN, server._REVIEW_SHOWN_DUPLICATE, server._REVIEW_SHOWN_WITH_ERRORS):
        assert "out of date" in text
    assert "Do not call write_vault" in server._REVIEW_SHOWN_WITH_ERRORS
    assert "once" in server._REVIEW_UNSUPPORTED and "ask what to change" in server._REVIEW_UNSUPPORTED


def test_a_draft_that_is_a_duplicate_and_invalid_gets_the_errors_message(tmp_vault, monkeypatch):
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: True)
    out = _call("propose_save", {**GOOD, "title": "Central Hub Topic", "extra_fields": {}}).structuredContent
    assert out["message"] == server._REVIEW_SHOWN_WITH_ERRORS
    assert out["duplicate"]["uid"] == "hub00001" and "message" not in out["duplicate"]


def test_the_russian_skill_says_the_same_about_retries_stale_cards_and_late_saves():
    from pathlib import Path
    import loci
    ru = (Path(loci.__file__).parent / "skills" / "loci-save" / "SKILL.ru-RU.md").read_text(encoding="utf-8")
    for phrase in ("один раз", "устарела и нажимать её не нужно", "всё же прошло", "loci__propose_save"):
        assert phrase in ru, phrase


def test_the_errors_message_tells_the_model_what_the_card_can_and_cannot_fix():
    text = server._REVIEW_SHOWN_WITH_ERRORS
    assert "empty title" in text and "remove a relation" in text and "supply one" in text
    assert "Mention any `warnings`" in server._REVIEW_UNSUPPORTED

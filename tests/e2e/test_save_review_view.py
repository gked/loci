"""
tests/e2e/test_save_review_view.py
The save-review card (`ui://loci/node-view.html`) in Chromium, behind a fake host.

A real MCP App runs in a host's sandboxed iframe and talks to the server through
the host. This file is that host, in about forty lines of JS: it answers the
view's handshake, hands it the result of a real `propose_save` call, and
forwards every `tools/call` the view makes to the real FastMCP server over an
in-memory session, against a temp copy of the fixture vault. Nothing about the
server or the vault is mocked, so a save here really writes (or refuses to).

What it cannot prove is how Claude Desktop itself treats the view — whether it
asks permission for each tool call, or shows `ui/message` text to the user.
That needs the real host and is checked by hand.

The iframe carries the same restrictive CSP a host applies (`connect-src 'none'`),
so a view that quietly depends on the network fails here as it would there.
"""

import asyncio
import concurrent.futures
import json
import re

import pytest
from playwright.sync_api import expect

from loci import api, mcp_server as server
from loci.mcp_apps import node_view_html
from loci.tools.frontmatter import load_frontmatter

DRAFT = dict(
    type="document",
    title="Review card: a note about the hub",
    body="## Why\n\nThe **hub** links everything.\n\n- one\n- two\n\n`code` and a [link](https://example.com/x).\n",
    tags=["review-card"],
    summary="Used by the review-card browser test.",
    relations=[{"uid": "hub00001", "type": "about"}],
    extra_fields={"subtype": "note", "status": "evergreen"},
)

HOST_PAGE = """<!doctype html><meta charset=utf-8>
<body style="margin:0;background:#262624"><iframe id="v" sandbox="allow-scripts" csp="__CSP__"
  style="width:760px;border:0;display:block;height:120px"></iframe>
<script>
const VIEW = __VIEW__, ARGS = __ARGS__;
window.messages = []; window.links = []; window.protocol = [];
const f = document.getElementById("v"); f.srcdoc = VIEW;
const reply = (id, result) => f.contentWindow.postMessage({jsonrpc: "2.0", id, result}, "*");
const note = (method, params) => f.contentWindow.postMessage({jsonrpc: "2.0", method, params}, "*");
window.addEventListener("message", async (e) => {
  if (e.source !== f.contentWindow) return;
  const d = e.data; window.protocol.push(d.method || "response");
  if (d.method === "ui/initialize") {
    reply(d.id, {protocolVersion: "2026-01-26", hostCapabilities: {}, hostInfo: {name: "fake", version: "0"}, hostContext: {theme: "dark"}});
  } else if (d.method === "ui/notifications/initialized") {
    const r = await window.mcp_call("propose_save", ARGS);
    note("ui/notifications/tool-result", r);
  } else if (d.method === "tools/call") {
    reply(d.id, await window.mcp_call(d.params.name, d.params.arguments || {}));
  } else if (d.method === "ui/message" || d.method === "ui/update-model-context") {
    if (window.refuse) { f.contentWindow.postMessage({jsonrpc: "2.0", id: d.id, error: {code: -32000, message: "denied"}}, "*"); return; }
    window.messages.push(d.params); reply(d.id, {});
  } else if (d.method === "ui/open-link") {
    window.links.push(d.params.url); reply(d.id, {});
  } else if (d.method === "ui/notifications/size-changed") {
    f.style.height = d.params.height + "px";
  }
});
</script>"""


def _js(x):
    return json.dumps(x).replace("</", "<\\/")      # a literal </script> in the view would end the host script


def _call_server(name, args):
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def run():
        async with connect(server.mcp._mcp_server) as client:
            r = await client.call_tool(name, args)
            return r.model_dump(mode="json", by_alias=True, exclude_none=True)

    # Playwright's sync API owns this thread's event loop, so the session runs on another.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, run()).result()


@pytest.fixture(scope="session")
def base_url():
    """Shadows the suite's `base_url`, which starts the API and a vite build. pytest-playwright
    asks for it whether or not a test uses a page from it, and the card needs neither server."""
    return "about:blank"


@pytest.fixture
def page(browser):
    """A blank page from the suite's shared browser. Not the suite's `page`/`app_page`, and not a
    Playwright of our own: a second sync_playwright() cannot start beside the session's."""
    pg = browser.new_page()
    yield pg
    pg.close()


@pytest.fixture
def card(page, tmp_vault, monkeypatch):
    """Open the card on a draft and return a function that reopens it on another."""
    monkeypatch.setattr(server, "_client_supports_apps", lambda ctx: True)
    _call_server("list_vault", {})                  # seed meta/ so file counts below mean the card's doing
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.expose_function("mcp_call", _call_server)
    csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'"

    def open_card(**overrides):
        html = (HOST_PAGE.replace("__CSP__", csp)
                .replace("__VIEW__", _js(node_view_html()))
                .replace("__ARGS__", _js({**DRAFT, **overrides})))
        page.set_content(html)
        view = page.frame_locator("#v")
        expect(view.locator("[data-testid=nv-title], [data-testid=nv-title-input]").first).to_be_visible()
        return view

    open_card.errors = errors
    return open_card


def _nodes(vault, title):
    found = []
    for p in vault.glob("*.md"):
        fm, body = load_frontmatter(p.read_text(encoding="utf-8"))
        if fm and fm.get("title") == title:
            found.append((fm, body))
    return found


def _md_count(vault):
    return len(list(vault.glob("*.md")))


def _messages(page):
    """What the view has sent the chat. The send happens after the card redraws, so wait for it."""
    page.wait_for_function("window.messages.length > 0")
    return page.evaluate("window.messages")


# ---------------------------------------------------------------------------

def test_the_draft_shows_as_the_node_will_be_stored(card, tmp_vault):
    before = _md_count(tmp_vault)
    view = card()
    expect(view.locator("[data-testid=nv-title]")).to_have_text(DRAFT["title"])
    expect(view.locator("[data-testid=nv-type]")).to_have_text("document / note")
    expect(view.locator("[data-testid=nv-badge]")).to_contain_text("not saved")
    expect(view.locator("[data-testid=nv-tag]")).to_have_text("#review-card")
    expect(view.locator("[data-testid=nv-summary]")).to_have_text(DRAFT["summary"])
    rel = view.locator("[data-testid=nv-relation]")
    expect(rel).to_have_count(1)
    expect(rel).to_contain_text("Central Hub Topic")
    body = view.locator("[data-testid=nv-body]")
    expect(body.locator("h2")).to_have_text("Why")
    expect(body.locator("strong")).to_have_text("hub")
    expect(body.locator("li")).to_have_count(2)
    expect(body.locator("code")).to_have_text("code")
    expect(view.locator("[data-testid=nv-save]")).to_be_enabled()
    assert _md_count(tmp_vault) == before, "showing the draft wrote to the vault"
    assert card.errors == []


def test_save_writes_the_node_and_tells_the_assistant(card, tmp_vault, page):
    view = card()
    view.locator("[data-testid=nv-save]").click()
    saved = view.locator("[data-testid=nv-saved]")
    expect(saved).to_be_visible()
    [(fm, body)] = _nodes(tmp_vault, DRAFT["title"])
    assert fm["type"] == "document" and fm["tags"] == ["review-card"]
    assert fm["relations"] == [{"uid": "hub00001", "type": "about"}]
    assert "The **hub** links everything." in body
    expect(saved).to_contain_text(fm["uid"])
    expect(view.locator("[data-testid=nv-save]")).to_have_count(0)      # nothing left to click twice
    [msg] = _messages(page)
    text = msg["content"]["text"]
    assert fm["uid"] in text and "Saved" in text and "wrap-up" in text
    assert "edited" not in text.lower()
    assert card.errors == []


def test_an_edit_is_what_gets_saved_and_the_assistant_is_told(card, tmp_vault, page):
    view = card()
    view.locator("[data-testid=nv-edit]").click()
    view.locator("[data-testid=nv-title-input]").fill("Review card: edited title")
    view.locator("[data-testid=nv-tags-input]").fill("#Edited, second-tag")
    view.locator("[data-testid=nv-body-input]").fill("Rewritten body.\n")
    view.locator("[data-testid=nv-save]").click()
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()
    assert _nodes(tmp_vault, DRAFT["title"]) == []
    [(fm, body)] = _nodes(tmp_vault, "Review card: edited title")
    assert fm["tags"] == ["edited", "second-tag"]
    assert body.strip() == "Rewritten body."
    text = _messages(page)[0]["content"]["text"]
    assert "edited the draft" in text and "title" in text and "body" in text and "tags" in text


def test_preview_renders_the_edit_and_reset_restores_the_proposal(card, tmp_vault):
    view = card()
    view.locator("[data-testid=nv-edit]").click()
    view.locator("[data-testid=nv-body-input]").fill("# Changed\n")
    view.locator("[data-testid=nv-preview]").click()
    expect(view.locator("[data-testid=nv-body] h1")).to_have_text("Changed")
    view.locator("[data-testid=nv-reset]").click()
    expect(view.locator("[data-testid=nv-body] h2")).to_have_text("Why")
    expect(view.locator("[data-testid=nv-reset]")).to_have_count(0)


def test_a_relation_the_user_leaves_out_is_not_saved(card, tmp_vault):
    view = card()
    view.locator("[data-testid=nv-relation-toggle]").click()
    expect(view.locator("[data-testid=nv-relation]")).to_have_attribute("data-off", "true")
    view.locator("[data-testid=nv-save]").click()
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()
    [(fm, _)] = _nodes(tmp_vault, DRAFT["title"])
    assert not fm.get("relations")


def test_cmd_enter_saves(card, tmp_vault):
    view = card()
    view.locator("[data-testid=nv-title]").click()
    view.locator("body").press("Control+Enter")
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()
    assert len(_nodes(tmp_vault, DRAFT["title"])) == 1


def test_a_draft_with_errors_cannot_be_saved(card, tmp_vault):
    before = _md_count(tmp_vault)
    view = card(extra_fields={})
    expect(view.locator("[data-testid=nv-errors]")).to_contain_text("subtype")
    expect(view.locator("[data-testid=nv-save]")).to_be_disabled()
    assert _md_count(tmp_vault) == before


def test_a_similar_node_makes_the_user_choose_before_saving(card, tmp_vault):
    before = _md_count(tmp_vault)
    view = card(title="Central Hub Topic")
    expect(view.locator("[data-testid=nv-duplicate]")).to_contain_text("already exists")
    expect(view.locator("[data-testid=nv-save]")).to_be_disabled()
    view.locator("[data-testid=nv-dup-new]").click()
    save = view.locator("[data-testid=nv-save]")
    expect(save).to_have_text("Save anyway")
    save.click()
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()
    assert len(_nodes(tmp_vault, "Central Hub Topic")) == 2
    assert _md_count(tmp_vault) == before + 1


def test_updating_the_existing_node_hands_back_to_the_assistant_and_writes_nothing(card, tmp_vault, page):
    before = _md_count(tmp_vault)
    view = card(title="Central Hub Topic")
    view.locator("[data-testid=nv-dup-update]").click()
    expect(view.locator("[data-testid=nv-handoff]")).to_be_visible()
    text = _messages(page)[0]["content"]["text"]
    assert "hub00001" in text and "Do not save a new node" in text
    assert _md_count(tmp_vault) == before


def test_a_duplicate_that_appears_after_the_draft_is_still_caught(card, tmp_vault):
    """The draft check ran minutes ago. write_vault is the authority and re-checks on the click."""
    view = card()
    api.save(type="document", title=DRAFT["title"], body="made meanwhile", extra_fields={"subtype": "note", "status": "evergreen"})
    before = _md_count(tmp_vault)
    view.locator("[data-testid=nv-save]").click()
    expect(view.locator("[data-testid=nv-duplicate]")).to_be_visible()
    expect(view.locator("[data-testid=nv-saved]")).to_have_count(0)
    assert _md_count(tmp_vault) == before


def test_note_content_cannot_inject_markup_or_script(card, tmp_vault, page):
    hostile = (
        "<img src=x onerror=\"window.pwned=1\">\n\n<script>window.pwned=1</script>\n\n"
        "[bad](javascript:window.pwned=1) and [good](https://example.com/page)\n\n"
        "**<b>x</b>**\n"
    )
    view = card(body=hostile, title="<i>hostile</i> title")
    body = view.locator("[data-testid=nv-body]")
    expect(body).to_be_visible()
    assert body.locator("img, script, b, i").count() == 0
    expect(view.locator("[data-testid=nv-title]")).to_have_text("<i>hostile</i> title")
    assert page.frame_locator("#v").locator("html").evaluate("() => window.pwned === undefined")
    assert body.locator("a[href^='javascript']").count() == 0
    body.locator("a", has_text="good").click()
    assert page.evaluate("window.links") == ["https://example.com/page"]
    assert "bad" in body.inner_text()


def test_a_host_that_refuses_the_message_is_not_claimed_to_have_been_told(card, tmp_vault, page):
    view = card()
    page.evaluate("window.refuse = true")          # the host now declines every message from the view
    view.locator("[data-testid=nv-save]").click()
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()            # the node is saved regardless
    expect(view.locator("[data-testid=nv-not-notified]")).to_be_visible()
    assert len(_nodes(tmp_vault, DRAFT["title"])) == 1


def test_a_refused_hand_off_is_not_shown_as_sent(card, tmp_vault, page):
    view = card(title="Central Hub Topic")
    page.evaluate("window.refuse = true")
    view.locator("[data-testid=nv-dup-update]").click()
    expect(view.locator("[data-testid=nv-problem]")).to_contain_text("could not be messaged")
    expect(view.locator("[data-testid=nv-handoff]")).to_have_count(0)


def test_a_new_title_drops_the_stale_duplicate_warning_without_losing_the_next_click(card, tmp_vault):
    view = card(title="Central Hub Topic")
    expect(view.locator("[data-testid=nv-duplicate]")).to_be_visible()
    view.locator("[data-testid=nv-edit]").click()
    view.locator("[data-testid=nv-title-input]").fill("A title nothing else has")
    view.locator("[data-testid=nv-tags-input]").fill("kept")        # moving focus fires the title's change
    expect(view.locator("[data-testid=nv-duplicate]")).to_have_count(0)
    expect(view.locator("[data-testid=nv-tags-input]")).to_have_value("kept")
    view.locator("[data-testid=nv-save]").click()
    expect(view.locator("[data-testid=nv-saved]")).to_be_visible()
    [(fm, _)] = _nodes(tmp_vault, "A title nothing else has")
    assert fm["tags"] == ["kept"]


def test_the_frame_follows_the_content_both_ways(card, page):
    view = card(body="line\n\n" * 60)
    tall = page.evaluate("document.getElementById('v').getBoundingClientRect().height")
    view.locator("[data-testid=nv-edit]").click()
    view.locator("[data-testid=nv-body-input]").fill("short")
    view.locator("[data-testid=nv-preview]").click()
    page.wait_for_function("document.getElementById('v').getBoundingClientRect().height < %d" % (tall - 200))


def test_the_view_speaks_only_the_documented_protocol(card, page):
    card()
    seen = set(page.evaluate("window.protocol"))
    assert {"ui/initialize", "ui/notifications/initialized"} <= seen
    assert all(m == "response" or m.startswith(("ui/", "tools/")) for m in seen), seen

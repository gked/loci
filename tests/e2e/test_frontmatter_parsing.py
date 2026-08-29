"""
tests/e2e/test_frontmatter_parsing.py
A node whose frontmatter holds a '---' still reaches the browser.

The parser used to close the frontmatter block on the first '---' substring
anywhere in the file. A node carrying a rule inside a frontmatter value —
which is exactly what a body misrouted into `updates` produces — failed to
parse, so nx_graph dropped it and it vanished from the index, the search
results, and every neighbour list at once. Nothing in the UI said why.

That makes the line-anchored split a user-visible fix, not an internal one,
which is why it is asserted here in Chromium and not only in the unit suite.
"""

import json
import urllib.request

import pytest
from playwright.sync_api import expect

import vault_facts as vf

# Every spec here pins the overlay uid. See README "Running against a deployment".
pytestmark = pytest.mark.fixture_bound

UID = vf.RULE_IN_FRONTMATTER_UID


def test_node_with_a_rule_in_its_frontmatter_is_served(base_url):
    """Fails at the API layer first, so a break is unambiguous."""
    with urllib.request.urlopen(f"{base_url}/api/nodes?state=all") as r:
        uids = {n["uid"] for n in json.load(r)}

    assert UID in uids, (
        "the node carrying a '---' in its summary is missing from the graph — "
        "the frontmatter split is matching the rule inside the value again"
    )


def test_node_with_a_rule_in_its_frontmatter_renders_in_the_index(app_page):
    row = app_page.locator(f"[data-testid='node-row'][data-uid='{UID}']")
    expect(row).to_be_visible()


def test_node_with_a_rule_in_its_frontmatter_opens(app_page):
    """The whole value survives the round trip, not just the part before the rule."""
    app_page.locator(f"[data-testid='node-row'][data-uid='{UID}']").click()

    detail = app_page.locator("[data-testid='node-detail']")
    expect(detail).to_be_visible()
    expect(detail).to_have_attribute("data-uid", UID)
    expect(app_page.locator("[data-testid='fm-value'][data-field='uid']")).to_have_text(UID)
    expect(app_page.locator("[data-testid='node-body']")).to_contain_text(
        "line-anchored"
    )

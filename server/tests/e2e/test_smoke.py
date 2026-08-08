"""
server/tests/e2e/test_smoke.py
The app boots, reaches the API, and renders the vault.

These are the tests that fail first when the infrastructure itself is broken —
keep them cheap and unconditional.
"""

import json
import re
import urllib.request

import pytest
from playwright.sync_api import expect


def test_app_loads_and_renders_nodes(app_page):
    """The index renders rows backed by the real API, not an empty shell."""
    rows = app_page.locator("[data-testid='node-row']")
    expect(rows.first).to_be_visible()
    expect(rows).not_to_have_count(0)


def test_no_api_error_banner(app_page):
    """A healthy run must not surface the 'cannot reach API' banner."""
    expect(app_page.locator("[data-testid='api-error']")).to_have_count(0)


def test_row_count_matches_api(app_page, base_url):
    """
    The UI shows exactly the active, non-ghost nodes the API returns.

    App.jsx fetches state=all then filters archived and pathless nodes out by
    default, so this pins the client-side filter to the server's answer.
    """
    with urllib.request.urlopen(f"{base_url}/api/nodes?state=all") as r:
        api_nodes = json.load(r)

    expected = [n for n in api_nodes if n.get("state") != "archived" and n.get("path")]
    expect(app_page.locator("[data-testid='node-row']")).to_have_count(len(expected))


def test_rail_count_matches_visible_rows(app_page):
    """The rail's 'vault · N loci' figure agrees with the rendered index."""
    rail = app_page.locator("[data-testid='rail-count']")
    # Match the shape, not just "non-empty": Playwright treats a *missing*
    # attribute as not-equal to "", so not_to_have_attribute would pass when
    # data-count is gone and the int() below would raise TypeError instead.
    expect(rail).to_have_attribute("data-count", re.compile(r"^\d+$"))
    rail_count = int(rail.get_attribute("data-count"))
    expect(app_page.locator("[data-testid='node-row']")).to_have_count(rail_count)


@pytest.mark.fixture_bound
def test_overlay_fixtures_present(base_url):
    """
    Guards the overlay vault itself: if these uids stop appearing, the archived
    and ghost specs are silently testing nothing.
    """
    with urllib.request.urlopen(f"{base_url}/api/nodes?state=all") as r:
        uids = {n["uid"] for n in json.load(r)}

    assert "e2e00001" in uids, "archived overlay node missing"
    assert "e2e00002" in uids, "asset overlay node missing"
    assert "e2e00003" in uids, "ghost-parent overlay node missing"
    assert "e2e0dead" in uids, "ghost node missing — did someone create e2e0dead.md?"


@pytest.mark.fixture_bound
def test_recent_endpoint_is_populated(base_url):
    """
    Regression guard for the date-freshening step in conftest.

    The checked-in fixture vault carries static January 2026 dates; without the
    rewrite, nx_graph.recent()'s 30-day window returns nothing and the Recent
    section renders empty forever.
    """
    with urllib.request.urlopen(f"{base_url}/api/nodes/recent") as r:
        recent = json.load(r)
    assert len(recent) > 0, "recent is empty — date freshening in conftest broke"

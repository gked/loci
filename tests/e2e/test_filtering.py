"""
tests/e2e/test_filtering.py
Tag rail, type chips, and the archived / ghost toggles.

All filtering in the index is client-side (App.jsx computes `indexNodes` from a
single state=all fetch), so these specs pin that logic rather than the API.
"""

import pytest
from playwright.sync_api import expect

import vault_facts as vf

# Every count here comes from vault_facts, so none of these can pass against a
# deployment. See README "Running against a deployment".
pytestmark = pytest.mark.fixture_bound

ROWS = "[data-testid='node-row']"


def _rows(page):
    return page.locator(ROWS)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def test_tag_selection_filters_index(app_page):
    tag, expected = "python", vf.TAG_COUNTS["python"]
    app_page.locator(f"[data-testid='rail-tag'][data-tag='{tag}']").click()
    expect(_rows(app_page)).to_have_count(expected)


def test_tag_deselection_restores_full_index(app_page):
    chip = app_page.locator("[data-testid='rail-tag'][data-tag='python']")
    chip.click()
    expect(_rows(app_page)).to_have_count(vf.TAG_COUNTS["python"])

    chip.click()
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)


def test_tag_row_marks_itself_active(app_page):
    chip = app_page.locator("[data-testid='rail-tag'][data-tag='testing']")
    expect(chip).to_have_attribute("data-active", "false")
    chip.click()
    expect(chip).to_have_attribute("data-active", "true")


def test_switching_tags_replaces_the_filter(app_page):
    app_page.locator("[data-testid='rail-tag'][data-tag='python']").click()
    expect(_rows(app_page)).to_have_count(vf.TAG_COUNTS["python"])

    app_page.locator("[data-testid='rail-tag'][data-tag='ml']").click()
    expect(_rows(app_page)).to_have_count(vf.TAG_COUNTS["ml"])


# ---------------------------------------------------------------------------
# Type chips
# ---------------------------------------------------------------------------

def test_type_filter_narrows_index(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='document']").click()
    expect(_rows(app_page)).to_have_count(vf.TYPE_COUNTS["document"])


def test_type_filter_all_restores_index(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    expect(_rows(app_page)).to_have_count(vf.TYPE_COUNTS["task"])

    app_page.locator("[data-testid='type-filter'][data-type='all']").click()
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)


def test_every_type_count_matches(app_page):
    for node_type, expected in vf.TYPE_COUNTS.items():
        app_page.locator(f"[data-testid='type-filter'][data-type='{node_type}']").click()
        expect(_rows(app_page)).to_have_count(expected)


# ---------------------------------------------------------------------------
# Archived / ghost toggles
# ---------------------------------------------------------------------------

def test_archived_hidden_by_default(app_page):
    expect(app_page.locator(f"{ROWS}[data-uid='{vf.ARCHIVED_UIDS[0]}']")).to_have_count(0)


def test_archived_toggle_reveals_archived_node(app_page):
    app_page.locator("[data-testid='toggle-archived']").click()

    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE + len(vf.ARCHIVED_UIDS))
    archived = app_page.locator(f"{ROWS}[data-uid='{vf.ARCHIVED_UIDS[0]}']")
    expect(archived).to_be_visible()
    expect(archived).to_have_attribute("data-state", "archived")


def test_ghost_hidden_by_default(app_page):
    expect(app_page.locator(f"{ROWS}[data-uid='{vf.GHOST_UIDS[0]}']")).to_have_count(0)


def test_ghost_toggle_reveals_ghost_node(app_page):
    app_page.locator("[data-testid='toggle-ghost']").click()

    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE + len(vf.GHOST_UIDS))
    ghost = app_page.locator(f"{ROWS}[data-uid='{vf.GHOST_UIDS[0]}']")
    expect(ghost).to_be_visible()
    expect(ghost).to_have_attribute("data-state", "ghost")


def test_both_toggles_are_additive(app_page):
    app_page.locator("[data-testid='toggle-archived']").click()
    app_page.locator("[data-testid='toggle-ghost']").click()
    expect(_rows(app_page)).to_have_count(vf.TOTAL_GRAPH_NODES)


def test_toggles_are_reversible(app_page):
    toggle = app_page.locator("[data-testid='toggle-archived']")
    toggle.click()
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE + len(vf.ARCHIVED_UIDS))
    toggle.click()
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)


# ---------------------------------------------------------------------------
# Index text filter
# ---------------------------------------------------------------------------

def test_index_filter_input_narrows_rows(app_page):
    """
    `to_have_count` rather than a one-shot `.count()`: the latter samples the
    DOM once with no auto-wait and can read the pre-filter list under CI load.
    """
    app_page.get_by_placeholder("filter by uid or title…").fill(vf.INDEX_FILTER_TERM)
    expect(_rows(app_page)).to_have_count(vf.INDEX_FILTER_MATCHES)


def test_index_filter_no_match_shows_empty_state(app_page):
    app_page.get_by_placeholder("filter by uid or title…").fill(vf.SEARCH_MISS)
    expect(app_page.locator("[data-testid='index-empty']")).to_be_visible()
    expect(_rows(app_page)).to_have_count(0)

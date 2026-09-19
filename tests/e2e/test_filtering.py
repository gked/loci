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
# Subtype chips
# ---------------------------------------------------------------------------

STRIP = "[data-testid='subtype-strip']"


def _subtype_chip(page, subtype):
    return page.locator(f"[data-testid='subtype-filter'][data-subtype='{subtype}']")


def test_subtype_strip_absent_until_a_type_is_chosen(app_page):
    expect(app_page.locator(STRIP)).to_have_count(0)
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    expect(app_page.locator(STRIP)).to_have_count(1)


def test_subtype_chips_come_from_the_registry_with_counts(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()

    chips = app_page.locator("[data-testid='subtype-filter']")
    expect(chips).to_have_count(4)  # bug, feature, question, chore — the full enum, not just what's present
    for subtype, expected in vf.SUBTYPE_COUNTS["task"].items():
        expect(_subtype_chip(app_page, subtype)).to_have_attribute("data-count", str(expected))
    expect(_subtype_chip(app_page, "bug")).to_have_attribute("data-count", "0")


def test_subtype_chip_narrows_and_marks_itself_active(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='document']").click()
    chip = _subtype_chip(app_page, "spec")
    expect(chip).to_have_attribute("data-active", "false")

    chip.click()
    expect(chip).to_have_attribute("data-active", "true")
    expect(_rows(app_page)).to_have_count(vf.SUBTYPE_COUNTS["document"]["spec"])
    expect(app_page.locator("[data-testid='row-subtype']").first).to_have_text("spec")

    chip.click()
    expect(_rows(app_page)).to_have_count(vf.TYPE_COUNTS["document"])


def test_leaving_the_type_drops_the_subtype(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    _subtype_chip(app_page, "chore").click()
    expect(_rows(app_page)).to_have_count(vf.SUBTYPE_COUNTS["task"]["chore"])

    app_page.locator("[data-testid='type-filter'][data-type='document']").click()
    expect(_rows(app_page)).to_have_count(vf.TYPE_COUNTS["document"])
    expect(_subtype_chip(app_page, "note")).to_have_attribute("data-active", "false")


def test_subtype_does_not_follow_the_node_back_button_to_all(app_page):
    """Only handleNav cleared the subtype; NodeDetail's back button goes
    straight to "all", which used to arrive still narrowed to the subtype with
    no chip on screen to explain it."""
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    _subtype_chip(app_page, "feature").click()
    expect(_rows(app_page)).to_have_count(vf.SUBTYPE_COUNTS["task"]["feature"])

    app_page.locator("[data-testid='node-row'][data-uid='aaa00001']").click()
    expect(app_page.locator("[data-testid='node-detail']")).to_be_visible()
    app_page.locator("[data-testid='node-back']").click()

    expect(app_page.locator("[data-testid='vault-index']")).to_be_visible()
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)
    expect(app_page.locator(STRIP)).to_have_count(0)


def test_recent_rows_show_the_same_subtype_as_all(app_page):
    """Recent is fed by /api/nodes/recent, a separate payload from the one the
    All view filters client-side; it used to omit subtype, so the same node
    read `task` in Recent and `task · feature` in All."""
    def subtype_by_uid():
        out = {}
        for row in _rows(app_page).all():
            label = row.locator("[data-testid='row-subtype']")
            out[row.get_attribute("data-uid")] = label.text_content() if label.count() else None
        return out

    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)
    in_all = subtype_by_uid()

    app_page.locator("[data-testid='rail-row'][data-rail-id='recent']").click()
    expect(_rows(app_page)).not_to_have_count(0)
    in_recent = subtype_by_uid()

    assert any(in_recent.values()), "Recent shows no subtype labels at all"
    assert in_recent == {uid: in_all[uid] for uid in in_recent}


def test_type_chips_include_every_registry_type(app_page):
    # `log` is canonical but was missing from the bundle's hardcoded list.
    expect(app_page.locator("[data-testid='type-filter'][data-type='log']")).to_have_count(1)


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

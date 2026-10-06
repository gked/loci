"""
tests/e2e/test_filtering.py
Type chips, subtype rail, and the archived / ghost toggles.

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
        if node_type == vf.USER_TYPE:
            continue  # no top-bar chip: it lives in the rail (user-type specs below)
        app_page.locator(f"[data-testid='type-filter'][data-type='{node_type}']").click()
        expect(_rows(app_page)).to_have_count(expected)


def test_parent_type_view_includes_its_user_types_nodes(app_page):
    app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE_PARENT}']").click()
    expect(_rows(app_page)).to_have_count(vf.TYPE_COUNTS.get(vf.USER_TYPE_PARENT, 0) + vf.TYPE_COUNTS[vf.USER_TYPE])


def test_clicking_the_open_rail_type_clears_it(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    app_page.locator("[data-testid='rail-type'][data-type='task']").click()
    expect(app_page.locator("[data-testid='rail-type-group'][data-open='true']")).to_have_count(0)
    expect(_rows(app_page)).to_have_count(vf.DEFAULT_VISIBLE)


# ---------------------------------------------------------------------------
# Subtype chips
# ---------------------------------------------------------------------------

STRIP = "[data-testid='subtype-strip']"


def _subtype_chip(page, subtype):
    return page.locator(f"[data-testid='subtype-filter'][data-subtype='{subtype}']")


def test_rail_lists_every_main_type_collapsed_until_one_is_chosen(app_page):
    groups = app_page.locator("[data-testid='rail-type-group']")
    expect(groups).not_to_have_count(0)
    expect(app_page.locator("[data-testid='rail-type-group'][data-open='true']")).to_have_count(0)

    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    open_groups = app_page.locator("[data-testid='rail-type-group'][data-open='true']")
    expect(open_groups).to_have_count(1)
    expect(open_groups).to_have_attribute("data-type", "task")


def test_subtypes_live_in_the_left_rail_not_the_index(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    expect(app_page.locator(f"aside {STRIP}")).to_have_count(1)
    expect(app_page.locator(f"[data-testid='vault-index'] {STRIP}")).to_have_count(0)
    expect(app_page.locator("[data-testid='rail-tag']")).to_have_count(0)


def test_choosing_a_rail_type_selects_it_and_moves_the_open_group(app_page):
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    app_page.locator("[data-testid='rail-type'][data-type='document']").click()
    expect(app_page.locator("[data-testid='type-filter'][data-type='document']")).to_have_attribute("data-active", "true")
    expect(app_page.locator("[data-testid='rail-type-group'][data-open='true']")).to_have_attribute("data-type", "document")


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


# ---------------------------------------------------------------------------
# User-defined types (rail "yours" group)
# ---------------------------------------------------------------------------

USER_STRIP = "[data-testid='usertype-strip']"


def _user_chip(page):
    return page.locator(f"[data-testid='usertype-filter'][data-usertype='{vf.USER_TYPE}']")


def test_user_types_are_not_in_the_top_bar(app_page):
    expect(app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE}']")).to_have_count(0)
    expect(app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE_PARENT}']")).to_have_count(1)


def test_user_type_sits_under_its_parent_in_the_rail(app_page):
    expect(app_page.locator(USER_STRIP)).to_have_count(0)

    app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE_PARENT}']").click()
    group = app_page.locator(f"[data-testid='rail-type-group'][data-type='{vf.USER_TYPE_PARENT}']")
    expect(group.locator(USER_STRIP)).to_have_count(1)
    expect(_user_chip(app_page)).to_have_attribute("data-count", "1")

    # Another type's group does not show it.
    app_page.locator("[data-testid='type-filter'][data-type='task']").click()
    expect(app_page.locator(USER_STRIP)).to_have_count(0)


def test_parent_type_view_includes_the_user_type_nodes(app_page):
    app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE_PARENT}']").click()
    expect(_rows(app_page)).to_have_count(1)
    expect(app_page.locator(f"[data-testid='node-row'][data-uid='{vf.USER_TYPE_UID}']")).to_have_count(1)


def test_rail_type_header_reports_whether_its_group_is_open(app_page):
    header = app_page.locator("[data-testid='rail-type'][data-type='task']")
    expect(header).to_have_attribute("aria-expanded", "false")
    assert header.get_attribute("aria-controls") is None

    header.click()
    expect(header).to_have_attribute("aria-expanded", "true")
    controls = header.get_attribute("aria-controls")
    expect(app_page.locator(f"[id='{controls}']")).to_have_count(1)


def test_user_type_row_narrows_and_clears(app_page):
    app_page.locator(f"[data-testid='type-filter'][data-type='{vf.USER_TYPE_PARENT}']").click()
    chip = _user_chip(app_page)
    chip.click()
    expect(chip).to_have_attribute("data-active", "true")
    expect(_rows(app_page)).to_have_count(1)

    chip.click()
    expect(chip).to_have_attribute("data-active", "false")
    expect(_rows(app_page)).to_have_count(1)  # the parent view still has it

"""
tests/e2e/test_navigation.py
Moving between the index, node detail, and the command palette.

The app has no router — App.jsx drives everything off a `section` state value,
so "navigation" here means asserting the right screen mounted, not a URL change.
"""

import pytest
from playwright.sync_api import expect

import vault_facts as vf

# Every spec here opens a fixture node by uid, so none of them can pass against
# a deployment. See README "Running against a deployment".
pytestmark = pytest.mark.fixture_bound

# Open nodes by explicit uid, never `.first`. Many fixture uids 404 on
# /api/nodes/{uid} — see the KNOWN DEFECT note in vault_facts.py.
OPEN_UID = "bbb00001"


def _open(page, uid):
    page.locator(f"[data-testid='node-row'][data-uid='{uid}']").click()
    detail = page.locator("[data-testid='node-detail']")
    expect(detail).to_be_visible()
    return detail


# ---------------------------------------------------------------------------
# Index -> detail -> back
# ---------------------------------------------------------------------------

def test_click_row_opens_node_detail(app_page):
    detail = _open(app_page, OPEN_UID)
    expect(detail).to_have_attribute("data-uid", OPEN_UID)


def test_detail_renders_title_frontmatter_and_body(app_page):
    _open(app_page, OPEN_UID)

    expect(app_page.locator("[data-testid='node-title']")).not_to_be_empty()
    expect(app_page.locator("[data-testid='node-frontmatter']")).to_be_visible()
    expect(app_page.locator("[data-testid='node-body']")).to_be_visible()

    # The uid row in the frontmatter grid must agree with the container.
    expect(
        app_page.locator("[data-testid='fm-value'][data-field='uid']")
    ).to_have_text(OPEN_UID)


def test_detail_title_matches_the_row_clicked(app_page):
    row_title = app_page.locator(
        f"[data-testid='node-row'][data-uid='{OPEN_UID}'] .lr-title"
    ).inner_text()
    _open(app_page, OPEN_UID)
    expect(app_page.locator("[data-testid='node-title']")).to_have_text(row_title)


def test_back_button_returns_to_index(app_page):
    _open(app_page, OPEN_UID)

    app_page.locator("[data-testid='node-back']").click()
    expect(app_page.locator("[data-testid='vault-index']")).to_be_visible()
    expect(app_page.locator("[data-testid='node-detail']")).to_have_count(0)


def test_escape_returns_to_index(app_page):
    """App.jsx binds Escape to leaving the node section."""
    _open(app_page, OPEN_UID)

    app_page.keyboard.press("Escape")
    expect(app_page.locator("[data-testid='vault-index']")).to_be_visible()


def test_asset_node_detail_renders_the_asset_block(app_page):
    """
    Asserts on the rendered asset block, not just that the node opened.

    api.get() swallows a failed resolve and appends `asset_content: null /
    asset_error: …` instead of raising (src/loci/api.py:249), so a spec that only
    checks data-uid stays green if the asset file goes missing or loci_root
    stops resolving — and this is the suite's only asset coverage.
    """
    detail = _open(app_page, vf.ASSET_UID)
    expect(detail).to_have_attribute("data-uid", vf.ASSET_UID)

    block = app_page.locator("[data-testid='node-asset']")
    expect(block).to_be_visible()
    expect(block).to_have_attribute("data-mime", vf.ASSET_MIME)
    expect(block).to_contain_text(vf.ASSET_FILENAME)
    expect(app_page.locator("[data-testid='node-asset-content']")).to_have_text(
        vf.ASSET_CONTENT.strip()
    )


# ---------------------------------------------------------------------------
# Command palette
# ---------------------------------------------------------------------------

def test_palette_opens_via_keyboard(app_page):
    app_page.keyboard.press("Meta+k")
    expect(app_page.locator("[data-testid='command-palette']")).to_be_visible()


def test_palette_opens_via_rail(app_page):
    app_page.locator("[data-testid='rail-row'][data-rail-id='cmd']").click()
    expect(app_page.locator("[data-testid='command-palette']")).to_be_visible()


def test_palette_closes_on_escape(app_page):
    app_page.locator("[data-testid='rail-row'][data-rail-id='cmd']").click()
    expect(app_page.locator("[data-testid='command-palette']")).to_be_visible()

    app_page.keyboard.press("Escape")
    expect(app_page.locator("[data-testid='command-palette']")).to_have_count(0)


def test_palette_search_returns_results(app_page):
    """
    Waits for the specific expected uid, not just "a result".

    The palette renders recent nodes until the 150ms-debounced query resolves,
    so a generic `.first` assertion would pass against the recent list and prove
    nothing about search.
    """
    app_page.locator("[data-testid='rail-row'][data-rail-id='cmd']").click()
    app_page.locator("[data-testid='palette-input']").fill(vf.SEARCH_HIT)

    expect(
        app_page.locator(f"[data-testid='palette-result'][data-uid='{vf.SEARCH_HIT_UID}']")
    ).to_be_visible()
    expect(app_page.locator("[data-testid='palette-result']")).to_have_count(vf.SEARCH_HIT_COUNT)


def test_palette_result_opens_node(app_page):
    app_page.locator("[data-testid='rail-row'][data-rail-id='cmd']").click()
    app_page.locator("[data-testid='palette-input']").fill(vf.SEARCH_HIT)

    # Settle on the search result before clicking — otherwise the debounce can
    # swap the list out from under the click.
    result = app_page.locator(f"[data-testid='palette-result'][data-uid='{vf.SEARCH_HIT_UID}']")
    expect(result).to_be_visible()
    result.click()

    expect(app_page.locator("[data-testid='command-palette']")).to_have_count(0)
    expect(app_page.locator("[data-testid='node-detail']")).to_have_attribute(
        "data-uid", vf.SEARCH_HIT_UID
    )


def test_skill_node_detail_shows_its_latin_name_and_type(app_page):
    detail = _open(app_page, vf.SKILL_UID)
    expect(detail).to_contain_text("ars · skill")

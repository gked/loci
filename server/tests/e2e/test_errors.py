"""
server/tests/e2e/test_errors.py
Failure and empty states.

These use the raw `page` fixture rather than `app_page` because the route
interception has to be installed before the first load.
"""

from playwright.sync_api import expect

import vault_facts as vf

# React Query retries failed queries 3x with exponential backoff before
# surfacing isError, so the banner takes several seconds to appear. That 3 is
# the library default — app/src/main.jsx sets only staleTime — so if a `retry`
# option is ever added there, revisit this timeout.
ERROR_TIMEOUT_MS = 30_000


def test_api_failure_shows_error_banner(page, base_url):
    """
    Proves the suite is exercising a real backend: cut the API off and the UI
    must say so. If this passed against a mock, the mock would be the bug.
    """
    page.route("**/api/nodes**", lambda route: route.abort())
    page.goto(base_url)

    expect(page.locator("[data-testid='api-error']")).to_be_visible(timeout=ERROR_TIMEOUT_MS)


def test_api_failure_leaves_index_empty(page, base_url):
    page.route("**/api/nodes**", lambda route: route.abort())
    page.goto(base_url)

    expect(page.locator("[data-testid='api-error']")).to_be_visible(timeout=ERROR_TIMEOUT_MS)
    expect(page.locator("[data-testid='node-row']")).to_have_count(0)


def test_server_error_response_shows_banner(page, base_url):
    """A 500 is handled the same way as an unreachable host."""
    page.route("**/api/nodes**", lambda route: route.fulfill(status=500, body="boom"))
    page.goto(base_url)

    expect(page.locator("[data-testid='api-error']")).to_be_visible(timeout=ERROR_TIMEOUT_MS)


def test_palette_search_with_no_matches(app_page):
    app_page.locator("[data-testid='rail-row'][data-rail-id='cmd']").click()
    app_page.locator("[data-testid='palette-input']").fill(vf.SEARCH_MISS)

    expect(app_page.locator("[data-testid='palette-empty']")).to_be_visible()
    expect(app_page.locator("[data-testid='palette-result']")).to_have_count(0)


def test_recovers_after_api_returns(page, base_url):
    """
    The banner is not sticky: once the API answers again, a reload renders the
    vault normally. Guards against error state leaking into the happy path.
    """
    page.route("**/api/nodes**", lambda route: route.abort())
    page.goto(base_url)
    expect(page.locator("[data-testid='api-error']")).to_be_visible(timeout=ERROR_TIMEOUT_MS)

    page.unroute("**/api/nodes**")
    page.reload()

    expect(page.locator("[data-testid='node-row']").first).to_be_visible()
    expect(page.locator("[data-testid='api-error']")).to_have_count(0)

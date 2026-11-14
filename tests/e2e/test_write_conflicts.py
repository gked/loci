"""
tests/e2e/test_write_conflicts.py
A sync tool left a "(conflicted copy …)" note: the rail offers to merge it, and
the user picks a side where both computers changed the same line.

The files are written into the session vault and removed again. They carry no
frontmatter, so they are never nodes and no count in vault_facts.py moves.

This is the one spec that writes through the UI, and the merge is a recorded
change. test_smoke.py asserts the vault has no change to undo, so this file must
run after it: keep its name sorting after "test_smoke".
"""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.fixture_bound

NOTE = "e2e-conflict-demo.md"
COPY = "e2e-conflict-demo (conflicted copy 2026-11-14 081923).md"


@pytest.fixture
def conflicted(e2e_vault):
    (e2e_vault / NOTE).write_text("shared line\nmine\n", encoding="utf-8")
    (e2e_vault / COPY).write_text("shared line\ntheirs\n", encoding="utf-8")
    yield
    (e2e_vault / NOTE).unlink(missing_ok=True)
    (e2e_vault / COPY).unlink(missing_ok=True)


def test_a_vault_without_copies_shows_no_merge_control(app_page):
    expect(app_page.locator("[data-testid='merge-conflicts']")).to_have_count(0)


def test_the_user_picks_a_side_and_the_copy_is_merged(app_page, conflicted, e2e_vault):
    app_page.reload()
    panel = app_page.locator("[data-testid='merge-conflicts']")
    expect(panel).to_have_attribute("data-count", "1")

    panel.locator("[data-testid='conflicts-toggle']").click()
    item = panel.locator("[data-testid='conflict-item']")
    expect(item).to_have_attribute("data-kind", "conflict")
    apply = item.locator("[data-testid='conflict-apply']")
    expect(apply).to_be_disabled()          # no side chosen yet

    item.locator("[data-testid='conflict-pick-b']").click()
    expect(item.locator("[data-testid='conflict-pick-b']")).to_have_attribute("data-active", "true")
    expect(apply).to_be_enabled()
    apply.click()

    expect(app_page.locator("[data-testid='merge-conflicts']")).to_have_count(0)
    assert (e2e_vault / NOTE).read_text(encoding="utf-8") == "shared line\ntheirs\n"
    assert not (e2e_vault / COPY).exists()

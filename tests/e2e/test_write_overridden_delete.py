"""
tests/e2e/test_write_overridden_delete.py
A note deleted on one computer and edited on the other keeps the edit. The app
warns on the note and offers to delete it again.

The note is made through the rail's merge control (a "(conflicted copy …)" file
whose original is gone) and the last step deletes it again, so the vault ends as
it began and no count in vault_facts.py moves. It writes, so it must sort after
test_smoke.py.
"""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.fixture_bound

UID = "e2e0de1e"
NOTE = "e2e-overridden-delete.md"
COPY = "e2e-overridden-delete (conflicted copy 2026-11-14 081923).md"
TEXT = f"""---
uid: {UID}
type: document
subtype: note
status: draft
title: E2E overridden delete
summary: Edited on one computer after it was deleted on another.
created_at: '2026-11-14T08:00:00Z'
updated_at: '2026-11-14T08:19:23Z'
---

Edited after the delete.
"""


@pytest.fixture
def lost_delete(e2e_vault):
    (e2e_vault / COPY).write_text(TEXT, encoding="utf-8")
    yield
    (e2e_vault / COPY).unlink(missing_ok=True)
    (e2e_vault / NOTE).unlink(missing_ok=True)


def restore_the_note(app_page):
    app_page.reload()
    panel = app_page.locator("[data-testid='merge-conflicts']")
    panel.locator("[data-testid='conflicts-toggle']").click()
    item = panel.locator("[data-testid='conflict-item']")
    expect(item).to_have_attribute("data-kind", "restore")
    item.locator("[data-testid='conflict-apply']").click()
    expect(app_page.locator("[data-testid='merge-conflicts']")).to_have_count(0)


def test_the_note_warns_and_can_be_deleted_again(app_page, lost_delete, e2e_vault):
    restore_the_note(app_page)
    assert (e2e_vault / NOTE).is_file()

    app_page.reload()
    app_page.locator(f"[data-testid='node-row'][data-uid='{UID}']").click()
    expect(app_page.locator("[data-testid='node-detail']")).to_have_attribute("data-uid", UID)
    warning = app_page.locator("[data-testid='overridden-delete']")
    expect(warning).to_be_visible()
    expect(app_page.locator("[data-testid='overridden-delete-text']")).to_contain_text("deleted on another computer")

    app_page.locator("[data-testid='overridden-delete-again']").click()

    expect(app_page.locator("[data-testid='node-detail']")).to_have_count(0)
    assert not (e2e_vault / NOTE).exists()
    expect(app_page.locator(f"[data-testid='node-row'][data-uid='{UID}']")).to_have_count(0)

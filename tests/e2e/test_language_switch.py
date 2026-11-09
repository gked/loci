"""
Switching the interface language to ru-RU and back.

The default is English, which every other spec relies on, so each test starts
from a clean browser context. The switch lives in the rail; the choice is kept
in the browser (localStorage) and wins over the server's configured language.
"""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.fixture_bound

RAIL_ALL = "[data-testid='rail-row'][data-rail-id='all']"


def test_the_interface_is_english_by_default(app_page):
    expect(app_page.locator(RAIL_ALL)).to_contain_text("All loci")
    expect(app_page.locator("[data-testid='lang-en']")).to_have_attribute("data-active", "true")
    expect(app_page.locator("html")).to_have_attribute("lang", "en")


def test_switching_to_russian_translates_the_interface(app_page):
    app_page.locator("[data-testid='lang-ru-RU']").click()

    expect(app_page.locator(RAIL_ALL)).to_contain_text("Все loci")
    expect(app_page.locator("[data-testid='lang-ru-RU']")).to_have_attribute("data-active", "true")
    expect(app_page.locator("html")).to_have_attribute("lang", "ru")
    expect(app_page.get_by_placeholder("фильтр по uid или названию…")).to_be_visible()
    # Identifiers are not translated: the type chips are registry names.
    expect(app_page.locator("[data-testid='type-filter'][data-type='project']")).to_be_visible()


def test_the_choice_survives_a_reload_and_can_be_undone(app_page):
    app_page.locator("[data-testid='lang-ru-RU']").click()
    app_page.reload()
    expect(app_page.locator(RAIL_ALL)).to_contain_text("Все loci")

    app_page.locator("[data-testid='lang-en']").click()
    expect(app_page.locator(RAIL_ALL)).to_contain_text("All loci")


def test_russian_reaches_the_palette_and_the_graph(app_page):
    app_page.locator("[data-testid='lang-ru-RU']").click()

    app_page.keyboard.press("Control+k")
    expect(app_page.get_by_placeholder("поиск по хранилищу — название, тег, uid")).to_be_visible()
    app_page.keyboard.press("Escape")

    app_page.locator("[data-testid='rail-row'][data-rail-id='graph']").click()
    expect(app_page.get_by_text("Топология").first).to_be_visible()

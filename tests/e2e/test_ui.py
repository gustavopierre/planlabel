import re

import pytest
from playwright.sync_api import expect

from planlabel.models import SlotResult
from tests.conftest import FakeAdvisor, FakeSource, make_application

pytestmark = pytest.mark.e2e


def open_app(page, server):
    page.goto(server.url)
    expect(page.locator("#work")).to_be_visible()
    return page


def wait_panels(page):
    for slot in (1, 2):
        expect(page.locator(f"#panel-{slot} .state", has_text="analisando")).to_have_count(0)


def checked(page, name):
    return page.locator(f'input[name="{name}"]:checked')


def test_E01_shows_application_and_counter(start_server, page):
    s = start_server()
    open_app(page, s)
    expect(page.locator("#app-meta")).to_contain_text("ABP")
    expect(page.locator("#app-meta")).to_contain_text("Meath County Council")
    expect(page.locator("#description")).to_contain_text("Description abp")
    expect(page.locator("#stats")).to_have_text("0 rotulados · 0 energia")


def test_E02_confirm_needs_category_and_subcategory(start_server, page):
    s = start_server(answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    expect(page.locator("#confirm")).to_be_disabled()
    page.get_by_label("Energia", exact=False).first.check()
    expect(page.locator("#confirm")).to_be_disabled()
    page.locator('input[name="subcategory"][value="wind"]').check()
    expect(page.locator("#confirm")).to_be_enabled()


def test_E03_label_wind_and_next(start_server, page):
    s = start_server(answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    first = page.locator("#description").inner_text()
    page.locator('input[name="category"][value="energy"]').check()
    page.locator('input[name="subcategory"][value="wind"]').check()
    page.locator("#confirm").click()
    expect(page.locator("#stats")).to_have_text("1 rotulados · 1 energia")
    expect(page.locator("#description")).not_to_have_text(first)
    assert s.label_count() == 1


def test_E04_subcategories_filtered_by_category(start_server, page):
    s = start_server(answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    expect(page.locator('input[name="subcategory"]')).to_have_count(0)
    page.locator('input[name="category"][value="energy"]').check()
    expect(page.locator('input[name="subcategory"]')).to_have_count(9)
    page.locator('input[name="subcategory"][value="bess"]').check()
    page.locator('input[name="category"][value="not_energy"]').check()
    expect(page.locator('input[name="subcategory"]')).to_have_count(2)
    expect(checked(page, "subcategory")).to_have_count(0)
    expect(page.locator('input[name="subcategory"][value="low_energy"]')).to_have_count(1)


def test_E05_translate_and_back(start_server, page):
    s = start_server()
    open_app(page, s)
    original = page.locator("#description").inner_text()
    page.locator("#translate").click()
    expect(page.locator("#description")).to_have_text(f"PT: {original}")
    expect(page.locator("#translate")).to_have_text("Ver original")
    page.locator("#translate").click()
    expect(page.locator("#description")).to_have_text(original)


def test_E06_cancel_next(start_server, page):
    s = start_server()
    open_app(page, s)
    first = page.locator("#description").inner_text()
    page.locator("#cancel").click()
    page.locator("#dialog-next").click()
    expect(page.locator("#description")).not_to_have_text(first)
    expect(page.locator("#stats")).to_have_text("0 rotulados · 0 energia")
    assert s.label_count() == 0


def test_E07_cancel_end(start_server, page):
    s = start_server()
    open_app(page, s)
    page.locator("#cancel").click()
    page.locator("#dialog-end").click()
    expect(page.locator("#ended")).to_be_visible()
    expect(page.locator("#ended-text")).to_have_text("Sessão encerrada. 0 registros rotulados.")
    assert s.label_count() == 0


def test_E08_keyboard(start_server, page):
    s = start_server(answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    page.keyboard.press("1")  # sem categoria: nada
    expect(checked(page, "subcategory")).to_have_count(0)
    page.keyboard.press("e")
    page.keyboard.press("9")
    expect(checked(page, "subcategory")).to_have_attribute("value", "data_centre")
    page.keyboard.press("n")
    page.keyboard.press("2")
    expect(checked(page, "subcategory")).to_have_attribute("value", "low_energy")
    page.keyboard.press("1")
    page.keyboard.press("Enter")
    expect(page.locator("#stats")).to_have_text("1 rotulados · 0 energia")
    assert s.repo.counts().by_subcategory["not_energy"] == 1


def test_E09_reload_new_application_counter_persists(start_server, page):
    s = start_server(answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    page.keyboard.press("e")
    page.keyboard.press("2")
    page.keyboard.press("Enter")
    expect(page.locator("#stats")).to_have_text("1 rotulados · 1 energia")
    before = page.locator("#description").inner_text()
    page.reload()
    expect(page.locator("#work")).to_be_visible()
    expect(page.locator("#stats")).to_have_text("1 rotulados · 1 energia")
    expect(page.locator("#description")).not_to_have_text(before)


def test_E10_source_error_and_retry(start_server, page):
    s = start_server()
    for src in s.sources:
        src.fail = True
    page.goto(s.url)
    expect(page.locator("#error")).to_be_visible()
    expect(page.locator("#error-text")).to_contain_text("Nenhuma fonte")
    for src in s.sources:
        src.fail = False
    page.locator("#retry").click()
    expect(page.locator("#work")).to_be_visible()


def test_E11_panels_show_all_percentages_and_highlight(start_server, page):
    s = start_server(answer1=("wind", "energy"), answer2=("wind", "not_energy"))
    open_app(page, s)
    wait_panels(page)
    for slot in (1, 2):
        panel = page.locator(f"#panel-{slot}")
        expect(panel.locator(".subs span")).to_have_count(11)
        expect(panel.locator(".subs .max")).to_have_text("wind 100")
        expect(panel.locator(".cats > span:not(.contradiction)")).to_have_count(2)
    expect(page.locator("#panel-1 .cats .max")).to_have_text("energia 100 %")
    expect(page.locator("#panel-1 .contradiction")).to_have_count(0)
    expect(page.locator("#panel-2 .cats .max")).to_have_text("não energia 100 %")
    expect(page.locator("#panel-2 .contradiction")).to_have_text("⚠ contradição")
    expect(page.locator("#panel-2 h2")).to_have_text("Modelo 2 · typesafe/jev-1.14")
    assert s.label_count() == 0


def test_E12_end_with_decisions_writes_nothing(start_server, page):
    s = start_server()
    open_app(page, s)
    wait_panels(page)
    page.keyboard.press("Escape")
    page.locator("#dialog-end").click()
    expect(page.locator("#ended")).to_be_visible()
    assert s.label_count() == 0


def test_E13_full_agreement_prefills_and_user_changes(start_server, page):
    s = start_server(answer1=("wind", "energy"), answer2=("wind", "energy"))
    open_app(page, s)
    wait_panels(page)
    expect(checked(page, "category")).to_have_attribute("value", "energy")
    expect(checked(page, "subcategory")).to_have_attribute("value", "wind")
    expect(page.locator("#badge")).to_have_text("sugestão dos dois modelos")
    assert s.label_count() == 0
    page.keyboard.press("4")
    expect(page.locator("#badge")).to_have_text("alterado por você")
    page.locator("#confirm").click()
    expect(page.locator("#stats")).to_have_text("1 rotulados · 1 energia")
    assert s.repo.counts().by_subcategory["bess"] == 1


def test_E14_user_choice_not_overwritten_by_late_decisions(start_server, page):
    s = start_server(answer1=("solar", "energy"), answer2=("solar", "energy"), delay=1.5)
    open_app(page, s)
    page.keyboard.press("e")
    page.keyboard.press("2")
    wait_panels(page)
    expect(page.locator("#panel-1 .subs .max")).to_have_text("solar 100")
    expect(checked(page, "subcategory")).to_have_attribute("value", "wind")
    expect(page.locator("#badge")).to_have_text("")


def test_E15_failed_model_shows_no_suggestion(start_server, page):
    s = start_server(answer1=None, answer2=("wind", "energy"))
    open_app(page, s)
    wait_panels(page)
    expect(page.locator("#panel-1 .state")).to_have_text("sem sugestão")
    expect(page.locator("#panel-2 .subs .max")).to_have_text("wind 100")
    expect(checked(page, "category")).to_have_count(0)
    page.keyboard.press("n")
    page.keyboard.press("1")
    page.locator("#confirm").click()
    expect(page.locator("#stats")).to_have_text("1 rotulados · 0 energia")


def test_E16_quota_line_and_daily_limit_panel(start_server, page):
    s = start_server()
    open_app(page, s)
    wait_panels(page)
    quotas = page.locator("#quotas")
    expect(quotas).to_contain_text("gemini-decision-1 hoje 1/10.000")
    expect(quotas).to_contain_text("jev-1.14 hoje 1")
    expect(quotas).to_contain_text("Dúvida 0/1.000")
    page.keyboard.press("Escape")
    page.locator("#dialog-next").click()
    wait_panels(page)
    expect(quotas).to_contain_text("gemini-decision-1 hoje 2/10.000")

    exhausted = SlotResult(slot=1, model="gemini-decision-1", reason="quota_exhausted")
    s2 = start_server(answer1=exhausted)
    open_app(page, s2)
    wait_panels(page)
    expect(page.locator("#panel-1 .state")).to_have_text("limite diário atingido")


def test_E17_doubt_opinion_block_and_reenable(start_server, page):
    advisor = FakeAdvisor()
    s = start_server(advisor=advisor, answer1=None, answer2=None)
    open_app(page, s)
    wait_panels(page)
    page.keyboard.press("d")
    expect(page.locator("#opinion")).to_contain_text("Opinião do gemini-3.5-flash-lite")
    expect(page.locator("#opinion")).to_contain_text("energia / wind")
    expect(checked(page, "category")).to_have_count(0)
    assert s.label_count() == 0

    advisor.mode = "blocked"
    page.keyboard.press("Escape")
    page.locator("#dialog-next").click()
    expect(page.locator("#doubt")).to_be_disabled()
    expect(page.locator("#doubt")).to_have_attribute("title", re.compile("por minuto"))
    advisor.mode = "ok"
    expect(page.locator("#doubt")).to_be_enabled(timeout=12000)


def test_E18_partial_agreement(start_server, page):
    s = start_server(answer1=("wind", "energy"), answer2=("hybrid", "energy"))
    open_app(page, s)
    wait_panels(page)
    expect(checked(page, "category")).to_have_attribute("value", "energy")
    expect(checked(page, "subcategory")).to_have_count(0)
    expect(page.locator("#badge")).to_have_text("categoria sugerida pelos dois modelos")

    s2 = start_server(answer1=("wind", "energy"), answer2=("wind", "not_energy"))
    open_app(page, s2)
    wait_panels(page)
    expect(checked(page, "category")).to_have_count(0)

    s3 = start_server(answer1=("low_energy", "energy"), answer2=("low_energy", "energy"))
    open_app(page, s3)
    wait_panels(page)
    expect(checked(page, "category")).to_have_attribute("value", "energy")
    expect(checked(page, "subcategory")).to_have_count(0)


def test_E19_application_link(start_server, page):
    src = FakeSource("abp", {1: make_application("abp", 1, application_url="https://x.ie/1")})
    s = start_server(sources=[src])
    open_app(page, s)
    link = page.locator("#app-link")
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", "https://x.ie/1")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")

    src2 = FakeSource("abp", {1: make_application("abp", 1, application_url="")})
    s2 = start_server(sources=[src2])
    open_app(page, s2)
    expect(page.locator("#app-link")).to_be_hidden()

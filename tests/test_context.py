"""V-M-CONTEXT: разделы тегами, числа JSON-блоком, падение в полный контекст."""

import json
import pytest

from report_qa import config
from report_qa.context import build, render_sections, render_numbers, SYSTEM_PROMPT
from report_qa.parse import load_sections

pytestmark = pytest.mark.skipif(
    not (config.SECTIONS_JSON.exists() and config.TABLES_JSON.exists()),
    reason="нет артефактов разбора",
)


def test_sections_carry_id_and_pages():
    """Атрибуты тега дают атрибуцию без просьб к модели."""
    rendered = render_sections(load_sections()[:2])
    assert '<section id="' in rendered
    assert 'pages="' in rendered
    assert "</section>" in rendered


def test_section_text_is_not_escaped():
    """Текст лежит как есть: в JSON-строке он потребовал бы экранирования."""
    sections = [{"id": "x", "title": "T", "page_from": 1, "page_to": 2,
                 "text": 'Кавычки "внутри" и\nперенос строки'}]
    rendered = render_sections(sections)
    assert 'Кавычки "внутри" и\nперенос строки' in rendered


def test_numbers_block_is_valid_compact_json():
    payload = json.loads(render_numbers([
        {"t": "x", "m": "Выручка", "s": None, "p": "2025", "v": 1441.1, "u": "млрд_руб", "pg": 86, "src": "both"},
        {"t": "x", "m": "Пусто", "v": None, "pg": 1},
    ]))
    assert len(payload["numbers"]) == 1
    assert payload["numbers"][0]["v"] == 1441.1
    assert "src" not in payload["numbers"][0], "лишние поля раздувают контекст"


def test_numbers_present_in_every_mode():
    """Без чисел вопрос про цифры не закрыть даже при верном разделе."""
    for mode in ("full", "router"):
        ctx = build("Какая была выручка?", mode=mode, section_ids=["s001-об-отчете"])
        assert "<numbers>" in ctx.prompt
        assert "1441.1" in ctx.prompt or "1441,1" in ctx.prompt


def test_full_mode_covers_whole_document():
    ctx = build("Вопрос", mode="full")
    assert len(ctx.section_ids) == 9
    assert ctx.approx_tokens > 50_000, "полный контекст подозрительно мал"


def test_router_mode_is_much_smaller_than_full():
    """Ради этого роутер и нужен: 7-15k вместо 175k."""
    sections = load_sections()
    fin = next(s for s in sections if s["title"] == "Финансовые результаты")
    small = build("Какая была выручка?", mode="router", section_ids=[fin["id"]])
    full = build("Какая была выручка?", mode="full")
    assert small.approx_tokens < full.approx_tokens / 3


def test_empty_selection_falls_back_to_full():
    """Пустая выборка означала бы ответ без источника: падаем в полный контекст."""
    ctx = build("Вопрос", mode="router", section_ids=["нет-такого-раздела"])
    assert ctx.mode == "router->full"
    assert len(ctx.section_ids) == 9


def test_system_prompt_states_the_rules():
    for rule in ("ТОЛЬКО", "стр.", "не нашёл" if "не нашёл" in SYSTEM_PROMPT else "не хватает"):
        assert rule in SYSTEM_PROMPT

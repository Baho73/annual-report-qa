"""V-M-PARSE: разделы документа по встроенным закладкам."""

import pytest

from report_qa import config
from report_qa.parse import load_sections, toc_outline

SECTIONS = load_sections() if config.SECTIONS_JSON.exists() else []

pytestmark = pytest.mark.skipif(not SECTIONS, reason="нет data/sections.json, запустите python -m report_qa.parse")


def test_top_level_structure():
    """9 разделов верхнего уровня и 33 второго — как в закладках документа."""
    assert len([s for s in SECTIONS if s["level"] == 1]) == 9
    assert len([s for s in SECTIONS if s["level"] == 2]) == 33


def test_known_section_boundaries():
    """Границы ключевых разделов совпадают с проверенными вручную."""
    by_title = {s["title"]: s for s in SECTIONS if s["level"] == 1}
    fin = by_title["Финансовые результаты"]
    assert (fin["page_from"], fin["page_to"]) == (86, 97)
    gov = by_title["Корпоративное управление"]
    assert (gov["page_from"], gov["page_to"]) == (103, 125)


def test_top_level_covers_document_without_gaps():
    """Разделы верхнего уровня покрывают документ подряд, без дыр и нахлёстов."""
    top = sorted((s for s in SECTIONS if s["level"] == 1), key=lambda s: s["page_from"])
    for prev, nxt in zip(top, top[1:]):
        assert prev["page_to"] < nxt["page_from"], f'нахлёст: {prev["title"]} и {nxt["title"]}'
        assert nxt["page_from"] - prev["page_to"] == 1, f'дыра между {prev["title"]} и {nxt["title"]}'
    assert top[-1]["page_to"] == 201


def test_every_section_has_text_and_valid_range():
    for s in SECTIONS:
        assert s["page_from"] <= s["page_to"], s["title"]
        assert s["id"] and s["title"]
        assert isinstance(s["text"], str)


def test_section_ids_are_unique():
    ids = [s["id"] for s in SECTIONS]
    assert len(ids) == len(set(ids))


def test_toc_outline_is_small_enough_for_router():
    """Оглавление для роутера — тысячи символов, а не сотни тысяч."""
    outline = toc_outline(SECTIONS)
    assert len(outline) < 12000, "оглавление раздулось, роутер станет дорогим"
    assert "Финансовые результаты" in outline
    assert "стр." in outline

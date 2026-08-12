"""V-M-VECTOR: добросовестность контрольной ветки.

Смысл тестов — не в том, что поиск работает, а в том, что он сделан честно.
Соломенное чучело обесценивает весь замер и разбирается на защите за минуту.
"""

import pytest

from report_qa import config
from report_qa.parse import load_sections
from report_qa.vector import BM25, MAX_CHUNK_CHARS, build_chunks, search, section_ids_for

SECTIONS = load_sections() if config.SECTIONS_JSON.exists() else []
pytestmark = pytest.mark.skipif(not SECTIONS, reason="нет data/sections.json")


def test_chunks_follow_document_structure():
    """Чанк — смысловая единица, а не фиксированные N символов."""
    chunks = build_chunks(SECTIONS)
    assert chunks
    assert all(c.section_id and c.section_title for c in chunks)
    assert all(c.page_from <= c.page_to for c in chunks)


def test_no_parent_child_duplication():
    """Текст родителя не дублируется в чанках вместе с детьми.

    Именно на этом дубле полный контекст раздувался до 251k токенов.
    """
    chunks = build_chunks(SECTIONS)
    ids = [c.section_id for c in chunks]
    parents = {s["id"] for s in SECTIONS if s["level"] == 1}
    # Раздел верхнего уровня попадает в чанки только если у него нет детей.
    for pid in set(ids) & parents:
        section = next(s for s in SECTIONS if s["id"] == pid)
        children = [s for s in SECTIONS if s["level"] > 1
                    and section["page_from"] <= s["page_from"] <= section["page_to"]]
        assert not children, f"раздел {section['title']} попал в чанки вместе с детьми"


def test_heading_and_pages_are_inside_searchable_text():
    """Заголовок и страницы лежат в тексте, а не только в метаданных.

    Иначе запрос «риски» не находит раздел, где слово стоит в заголовке.
    """
    chunk = build_chunks(SECTIONS)[0]
    assert chunk.section_title in chunk.searchable
    assert f"стр. {chunk.page_from}" in chunk.searchable


def test_chunk_size_capped():
    assert all(len(c.text) <= MAX_CHUNK_CHARS + 1000 for c in build_chunks(SECTIONS))


def test_top_k_is_wide_enough():
    """k=8, а не 3: при узкой выборке проигрыш объяснялся бы окном, а не поиском."""
    assert config.THRESHOLDS["top_k"] >= 8


def test_lexical_search_finds_numbers():
    """Числа и точные термины — то, из чего состоит отчёт.

    Плотные эмбеддинги на них слабы, поэтому лексическая ветка обязательна.
    """
    bm25 = BM25([
        "Выручка группы составила 1441,1 млрд рублей",
        "Компания развивает облачные технологии и беспилотники",
        "Дивидендная политика и структура акционеров",
    ])
    assert bm25.top("1441,1 выручка", 1) == [0]


def test_search_returns_relevant_section_for_risks():
    """Запрос про риски приводит к разделу про риски, а не куда угодно."""
    ids = section_ids_for("Какие ключевые риски компания выделяет?", k=8)
    titles = {s["id"]: s["title"].lower() for s in SECTIONS}
    assert any("риск" in titles.get(i, "") for i in ids), \
        f"среди найденных разделов нет ни одного про риски: {[titles.get(i) for i in ids]}"


def test_search_respects_k():
    assert len(search("выручка", k=3)) <= 3

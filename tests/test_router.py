"""V-M-ROUTER: выбор разделов по оглавлению.

Модель не вызывается: проверяется логика разбора и расширения набора.
Живое поведение роутера проверяется прогоном замера.
"""

import json
import pytest

from report_qa import config, llm, router
from report_qa.parse import load_sections, toc_outline

SECTIONS = load_sections() if config.SECTIONS_JSON.exists() else []
pytestmark = pytest.mark.skipif(not SECTIONS, reason="нет data/sections.json")


def _fake_llm(monkeypatch, payload, text=None):
    def fake_call(prompt, role="answer", system=None, model=None, **kw):
        return llm.LLMResult(text=text if text is not None else json.dumps(payload),
                             model="fake", prompt_tokens=1500, completion_tokens=50)
    monkeypatch.setattr(router.llm, "call", fake_call)


def test_outline_includes_deep_headings():
    """Ключевые риски — заголовок четвёртого уровня.

    На оглавлении до второго уровня роутер физически не мог его выбрать:
    именно так и промахнулся первый прогон.
    """
    outline = toc_outline(SECTIONS, max_level=4)
    assert "Ключевые риски компании и управление ими" in outline


def test_outline_stays_cheap():
    """Полное оглавление — проценты от документа, экономия сохраняется."""
    outline = toc_outline(SECTIONS, max_level=4)
    assert len(outline) / 2.5 < 6000


def test_unknown_ids_are_dropped(monkeypatch):
    """Придуманный моделью раздел не попадает в контекст."""
    real = SECTIONS[5]["id"]
    _fake_llm(monkeypatch, {"sections": [real, "выдуманный-раздел"], "confidence": 0.9})
    decision = router.route("вопрос", SECTIONS)
    assert decision.section_ids == [real]


def test_empty_selection_means_full_document(monkeypatch):
    """Пустой выбор — не повод отвечать наугад."""
    _fake_llm(monkeypatch, {"sections": [], "confidence": 0.9})
    assert router.route("вопрос", SECTIONS).need_full is True


def test_unparseable_answer_falls_back_to_full(monkeypatch):
    _fake_llm(monkeypatch, None, text="я не понял вопрос")
    decision = router.route("вопрос", SECTIONS)
    assert decision.need_full is True
    assert decision.confidence == 0.0


def test_low_confidence_widens_selection(monkeypatch):
    """Низкая уверенность расширяет набор, а не сужает.

    Лишний раздел стоит копейки, потерянный — неверного ответа.
    """
    deep = next(s for s in SECTIONS if s["level"] >= 3)
    _fake_llm(monkeypatch, {"sections": [deep["id"]], "confidence": 0.3})
    decision = router.route("вопрос", SECTIONS)
    assert len(decision.section_ids) > 1, "набор не расширился при низкой уверенности"
    assert deep["id"] in decision.section_ids


def test_high_confidence_keeps_selection_tight(monkeypatch):
    deep = next(s for s in SECTIONS if s["level"] >= 3)
    _fake_llm(monkeypatch, {"sections": [deep["id"]], "confidence": 0.95})
    assert router.route("вопрос", SECTIONS).section_ids == [deep["id"]]


def test_need_full_flag_respected(monkeypatch):
    _fake_llm(monkeypatch, {"sections": [SECTIONS[3]["id"]], "confidence": 0.9, "need_full": True})
    decision = router.route("Стоит ли инвестировать?", SECTIONS)
    assert decision.need_full is True
    assert decision.mode == "full"

"""M-ROUTER: выбор разделов документа под вопрос."""

# FILE: report_qa/router.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: по оглавлению определить, какие разделы документа нужны для ответа, вместо подачи всего документа.
#   SCOPE: запрос к дешёвой модели с оглавлением, разбор выбора, расширение набора при низкой уверенности, признак полного контекста.
#   DEPENDS: M-LLM, M-PARSE, M-CONFIG
#   LINKS: M-ROUTER, V-M-ROUTER
#   INPUTS: вопрос, оглавление из data/sections.json
#   OUTPUTS: RouteDecision со списком разделов и уверенностью
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   RouteDecision - выбранные разделы, уверенность, признак нужен-весь-документ
#   route - выбор разделов под вопрос по оглавлению
#   ROUTER_PROMPT - инструкция роутеру: полнота важнее точности
# END_MODULE_MAP

import json
from dataclasses import dataclass, field
from typing import List, Optional

from report_qa import config, llm
from report_qa.parse import load_sections, toc_outline

__all__ = ["RouteDecision", "route", "ROUTER_PROMPT"]

# START_BLOCK_ROUTER_PROMPT
ROUTER_PROMPT = """Ты выбираешь разделы годового отчёта, нужные для ответа на вопрос.

Оглавление документа:
{outline}

Вопрос: {question}

Верни строгий JSON без пояснений:
{{"sections": ["<id раздела>", ...], "confidence": <0..1>, "need_full": <true|false>}}

Правила:
- Лишний раздел стоит копейки, потерянный стоит неверного ответа. При сомнении бери больше.
- Если ответ требует свести данные со всего документа (например, оценка компании
  целиком, сравнение множества направлений), ставь need_full=true.
- confidence — насколько ты уверен, что выбранных разделов достаточно.
- Идентификаторы бери из оглавления дословно.
"""
# END_BLOCK_ROUTER_PROMPT


# START_BLOCK_ROUTE
@dataclass
class RouteDecision:
    """Что подавать в большую модель и насколько мы в этом уверены."""

    section_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    need_full: bool = False
    raw: str = ""
    latency_s: float = 0.0
    tokens: int = 0

    @property
    def mode(self) -> str:
        return "full" if self.need_full else "router"


def route(question: str, sections: Optional[List[dict]] = None, model: Optional[str] = None) -> RouteDecision:
    """Разделы под вопрос.

    Роутеру подаётся только оглавление (2-3k токенов), поэтому шаг дёшев и
    может идти на быстрой модели: платить здесь за интеллект не за что.
    """
    sections = sections if sections is not None else load_sections()
    # Глубина 4, а не 2: «Ключевые риски компании и управление ими» — заголовок
    # четвёртого уровня, и на мелком оглавлении роутер физически не мог его
    # выбрать. Полное оглавление это ~4.3k токенов против 175k документа,
    # то есть 2.4 процента — экономия сохраняется, слепая зона исчезает.
    outline = toc_outline(sections, max_level=4)
    known = {s["id"] for s in sections}

    prompt = ROUTER_PROMPT.format(outline=outline, question=question)
    result = llm.call(prompt, role="router", model=model, max_tokens=800)

    try:
        parsed = llm.parse_json_response(result.text)
    except ValueError:
        # Неразобранный ответ роутера — не повод отвечать наугад.
        return RouteDecision(section_ids=[], confidence=0.0, need_full=True,
                             raw=result.text, latency_s=result.latency_s,
                             tokens=result.total_tokens)

    chosen = [s for s in (parsed.get("sections") or []) if s in known]
    confidence = float(parsed.get("confidence") or 0.0)
    need_full = bool(parsed.get("need_full")) or not chosen

    # Низкая уверенность расширяет набор, а не сужает: добавляем родительские
    # разделы верхнего уровня, внутрь которых попали выбранные.
    if not need_full and confidence < config.THRESHOLDS["router_min_confidence"]:
        by_id = {s["id"]: s for s in sections}
        spans = [(by_id[c]["page_from"], by_id[c]["page_to"]) for c in chosen if c in by_id]
        parents = [
            s["id"] for s in sections
            if s["level"] == 1 and any(s["page_from"] <= lo and hi <= s["page_to"] for lo, hi in spans)
        ]
        chosen = list(dict.fromkeys(chosen + parents))

    return RouteDecision(
        section_ids=chosen,
        confidence=confidence,
        need_full=need_full,
        raw=result.text,
        latency_s=result.latency_s,
        tokens=result.total_tokens,
    )
# END_BLOCK_ROUTE

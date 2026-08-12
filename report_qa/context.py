"""M-CONTEXT: сборка промпта под выбранный режим."""

# FILE: report_qa/context.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: собрать контекст для модели: текстовые разделы XML-тегами, числа и агрегаты JSON-блоком.
#   SCOPE: выбор разделов под режим, обрамление разделов тегами с провенансом, компактный JSON чисел.
#   DEPENDS: M-PARSE, M-AGG, M-CONFIG
#   LINKS: M-CONTEXT, V-M-CONTEXT
#   INPUTS: data/sections.json, data/tables_merged.json, data/aggregates.json
#   OUTPUTS: строка промпта и метаданные о поданных разделах
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   BuiltContext - собранный промпт вместе с перечнем поданных разделов и оценкой объёма
#   build - сборка контекста под режим full / router / vector
#   render_sections - разделы в XML-теги с идентификатором и диапазоном страниц
#   render_numbers - числа и агрегаты компактным JSON, подаются при любом режиме
#   SYSTEM_PROMPT - правила ответа: только из контекста, каждое число со страницей
# END_MODULE_MAP

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from report_qa import config
from report_qa.parse import load_sections, load_tables

__all__ = ["BuiltContext", "build", "render_sections", "render_numbers", "SYSTEM_PROMPT"]

# START_BLOCK_SYSTEM_PROMPT
SYSTEM_PROMPT = """Ты отвечаешь на вопросы по годовому отчёту публичной компании.

Правила, нарушение любого из них делает ответ негодным:

1. Отвечай ТОЛЬКО по тому, что подано в контексте. Знания о компании из других
   источников не используй, даже если уверен в них.
2. Каждое число сопровождай номером страницы в формате (стр. N). Номер бери из
   поля pg соответствующей записи или из атрибута pages раздела.
3. Если данных для ответа в контексте нет, так и скажи: назови, чего именно
   не хватает и что этот тип документа обычно не раскрывает. Не достраивай
   ответ по смыслу.
4. Не пересчитывай в уме то, что подано готовым. Приросты, доли и вклад в
   прирост уже посчитаны в блоке aggregates — бери оттуда.
5. Отвечай по-русски, коротко и по существу. Без вводных оборотов.
"""
# END_BLOCK_SYSTEM_PROMPT


# START_BLOCK_BUILT_CONTEXT
@dataclass
class BuiltContext:
    """Промпт и всё, что нужно знать о том, из чего он собран."""

    prompt: str
    mode: str
    section_ids: List[str] = field(default_factory=list)
    pages: List[int] = field(default_factory=list)
    chars: int = 0

    @property
    def approx_tokens(self) -> int:
        # Для русского текста примерно 2.5 символа на токен.
        return int(self.chars / 2.5)
# END_BLOCK_BUILT_CONTEXT


# START_BLOCK_RENDER
def render_sections(sections: List[dict]) -> str:
    """Разделы XML-тегами.

    XML, а не JSON: длинный текст внутри JSON-строки требует экранировать
    кавычки и переносы, и это стабильный источник поломок. В теге текст лежит
    как есть, а атрибуты pages дают модели готовую атрибуцию.
    """
    parts = []
    for s in sections:
        parts.append(
            f'<section id="{s["id"]}" title="{s["title"]}" '
            f'pages="{s["page_from"]}-{s["page_to"]}">\n{s["text"]}\n</section>'
        )
    return "\n\n".join(parts)


def render_numbers(records: List[dict], aggregates: Optional[dict] = None) -> str:
    """Числа и агрегаты компактным JSON.

    Подаются при ЛЮБОМ режиме: блок компактный, а без него вопрос про цифры
    не закрыть даже при верно выбранном разделе.
    """
    slim = [
        {k: v for k, v in r.items() if k in ("t", "m", "s", "p", "v", "u", "pg")}
        for r in records if r.get("v") is not None
    ]
    payload = {"numbers": slim}
    if aggregates:
        payload["aggregates"] = aggregates
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
# END_BLOCK_RENDER


# START_BLOCK_BUILD
def _load_aggregates() -> Optional[dict]:
    if not config.AGGREGATES_JSON.exists():
        return None
    with open(config.AGGREGATES_JSON, encoding="utf-8") as f:
        return json.load(f)


def build(
    question: str,
    mode: str = "full",
    section_ids: Optional[List[str]] = None,
    sections: Optional[List[dict]] = None,
    records: Optional[List[dict]] = None,
) -> BuiltContext:
    """Промпт под режим.

    full   — весь документ: разделы верхнего уровня покрывают его целиком.
    router — только разделы, выбранные роутером по оглавлению.
    vector — разделы, найденные векторной веткой (передаются section_ids).
    """
    sections = sections if sections is not None else load_sections()
    records = records if records is not None else load_tables()

    if mode == "full":
        chosen = [s for s in sections if s["level"] == 1]
    else:
        wanted = set(section_ids or [])
        chosen = [s for s in sections if s["id"] in wanted]
        if not chosen:
            # Пустая выборка означала бы ответ без источника. Падаем в полный
            # контекст: лишние токены дешевле неверного ответа.
            chosen = [s for s in sections if s["level"] == 1]
            mode = f"{mode}->full"

    # В режиме роутера сырые числа фильтруются по страницам выбранных разделов:
    # 868 записей это порядка 40k токенов, и без фильтра экономия от роутера
    # съедается целиком. Агрегаты подаются всегда — они компактны и закрывают
    # вопросы про рост, доли и вклад в прирост.
    aggregates = _load_aggregates()
    if mode.startswith("full"):
        relevant = records
    else:
        spans = [(s["page_from"], s["page_to"]) for s in chosen]
        relevant = [
            r for r in records
            if any(lo <= (r.get("pg") or -1) <= hi for lo, hi in spans)
        ]
        # Якорные страницы сводной таблицы сегментов нужны почти любому
        # числовому вопросу и стоят копейки.
        anchors = {21, 12}
        relevant += [r for r in records if r.get("pg") in anchors and r not in relevant]

    numbers_block = render_numbers(relevant, aggregates)
    sections_block = render_sections(chosen)

    prompt = (
        f"<question>{question}</question>\n\n"
        f"<numbers>\n{numbers_block}\n</numbers>\n\n"
        f"<document>\n{sections_block}\n</document>"
    )

    pages = sorted({p for s in chosen for p in (s["page_from"], s["page_to"])})
    return BuiltContext(
        prompt=prompt,
        mode=mode,
        section_ids=[s["id"] for s in chosen],
        pages=pages,
        chars=len(prompt),
    )
# END_BLOCK_BUILD

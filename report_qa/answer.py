"""M-ANSWER / M-GUARD / M-NUMCHECK: ответ с провенансом и границами."""

# FILE: report_qa/answer.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: получить ответ по документу со ссылками на страницы, проверить числа и удержать границы ответственности.
#   SCOPE: вызов модели поверх собранного контекста, извлечение цитат, детектор запроса рекомендации, сверка чисел ответа с контекстом.
#   DEPENDS: M-CONTEXT, M-LLM
#   LINKS: M-ANSWER, M-GUARD, M-NUMCHECK, V-M-ANSWER, V-M-GUARD, V-M-NUMCHECK
#   OUTPUTS: Answer с текстом, цитатами, флагами непроверенных чисел, токенами и ценой
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   Answer - результат: текст, цитаты, флаги, режим, токены, задержка, цена
#   ask - полный цикл ответа на вопрос в выбранном режиме
#   extract_citations - номера страниц, на которые сослался ответ
#   is_advice_request - детектор запроса инвестиционной рекомендации
#   ADVICE_NOTICE - блок про границы ответственности, добавляемый к такому ответу
#   check_numbers - числа ответа, которых нет в поданном контексте
#   numbers_in - все числа строки в нормализованном виде
# END_MODULE_MAP

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from report_qa import llm
from report_qa.context import SYSTEM_PROMPT, build

__all__ = [
    "Answer", "ask", "extract_citations", "is_advice_request",
    "ADVICE_NOTICE", "check_numbers", "numbers_in",
]

# START_BLOCK_GUARD
# Запрос оценки, а не факта. Ловим намерение, а не конкретную формулировку.
_ADVICE_RE = re.compile(
    r"стоит\s+ли\s+(инвестир|вклад|покуп|брать)|"
    r"(инвестиц\w+|покупк\w+)\s+рекоменд|"
    r"рекоменду\w*\s+(ли\s+)?(покуп|продав|инвестир)|"
    r"(покупать|продавать)\s+(ли\s+)?(акци|бумаг)|"
    r"хорош\w+\s+ли\s+(это\s+)?(вложен|инвестиц)|"
    r"выгодно\s+ли\s+(вклад|инвестир|покуп)|"
    r"should\s+i\s+(invest|buy)",
    re.I,
)

ADVICE_NOTICE = (
    "\n\n---\n"
    "Инвестиционную рекомендацию я не даю: это требует лицензии и знания вашего "
    "горизонта, налоговой ситуации и допустимого риска, которых у меня нет. "
    "Выше собраны факторы за и против из самого отчёта, со страницами. "
    "Решение остаётся за вами."
)


def is_advice_request(question: str) -> bool:
    """Запрос на оценку «покупать или нет», а не на факт из отчёта."""
    return bool(_ADVICE_RE.search(question or ""))
# END_BLOCK_GUARD


# START_BLOCK_NUMCHECK
_NUM_RE = re.compile(r"-?\d[\d   ]*(?:[.,]\d+)?")
# Годы и номера страниц числами не считаются: они дают ложные срабатывания.
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_PAGE_CITE_RE = re.compile(r"стр\.?\s*\d+", re.I)


def _values_in(text: str):
    """Числовые значения строки. Годы и ссылки на страницы отбрасываются."""
    cleaned = _PAGE_CITE_RE.sub(" ", text or "")
    values = []
    for raw in _NUM_RE.findall(cleaned):
        token = raw
        for space in (" ", " ", " ", " "):
            token = token.replace(space, "")
        token = token.replace(",", ".").rstrip(".")
        if not token or _YEAR_RE.match(token):
            continue
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def numbers_in(text: str) -> Set[str]:
    """Числа строки в нормализованном виде.

    «1 441,1», «1441.1» и «1441,1» — одно число: сравнивать надо значения,
    а не написание.
    """
    return {f"{v:.3f}".rstrip("0").rstrip(".") for v in _values_in(text)}


def _decimals(value: float) -> int:
    """Сколько знаков после запятой в записи числа."""
    text = repr(value)
    return len(text.split(".")[1]) if "." in text else 0


def check_numbers(answer_text: str, context_prompt: str) -> List[str]:
    """Числа ответа, которых нет в поданном контексте.

    Округление выдумкой не считается: модель, написавшая 35,8 там, где в
    контексте лежит 35,76, права. Число подтверждено, если в контексте есть
    значение, совпадающее с ним при округлении до той же точности.
    Без этой поблажки проверка даёт шум, и её перестают читать.
    """
    context_values = _values_in(context_prompt)
    if not context_values:
        return sorted(numbers_in(answer_text))

    unverified = []
    for value in _values_in(answer_text):
        # Допуск — половина единицы последнего разряда: 61,2 покрывает 61,15.
        # Через round() сравнивать нельзя: round(61.15, 1) в Python даёт 61.1,
        # потому что 61.15 не представимо в двоичном float точно.
        precision = min(_decimals(value), 3)
        tolerance = 0.5 * (10 ** -precision) + 1e-9
        if not any(abs(candidate - value) <= tolerance for candidate in context_values):
            unverified.append(f"{value:.3f}".rstrip("0").rstrip("."))
    return sorted(set(unverified))


# END_BLOCK_NUMCHECK


# START_BLOCK_ANSWER
@dataclass
class Answer:
    """Ответ вместе со всем, что нужно для доверия к нему."""

    text: str
    question: str
    mode: str
    cited_pages: List[int] = field(default_factory=list)
    section_ids: List[str] = field(default_factory=list)
    unverified_numbers: List[str] = field(default_factory=list)
    advice_guarded: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    model: str = ""

    @property
    def has_citations(self) -> bool:
        return bool(self.cited_pages)


def extract_citations(text: str) -> List[int]:
    """Страницы, на которые сослался ответ."""
    return sorted({int(m) for m in re.findall(r"стр\.?\s*(\d{1,3})", text or "", re.I)})


def ask(
    question: str,
    mode: str = "full",
    section_ids: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Answer:
    """Полный цикл: контекст, модель, проверка чисел, границы ответственности."""
    ctx = build(question, mode=mode, section_ids=section_ids)
    result = llm.call(ctx.prompt, role="answer", system=SYSTEM_PROMPT, model=model)

    text = result.text
    guarded = is_advice_request(question)
    if guarded:
        text = text + ADVICE_NOTICE

    return Answer(
        text=text,
        question=question,
        mode=ctx.mode,
        cited_pages=extract_citations(text),
        section_ids=ctx.section_ids,
        unverified_numbers=check_numbers(result.text, ctx.prompt),
        advice_guarded=guarded,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_s=result.latency_s,
        cost_usd=round(result.cost_usd, 4),
        model=result.model,
    )
# END_BLOCK_ANSWER

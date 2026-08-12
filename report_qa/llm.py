"""M-LLM: слой OpenRouter."""

# FILE: report_qa/llm.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: единственная точка обращения к моделям через OpenRouter с обязательным таймаутом, счётчиком токенов и замером задержки.
#   SCOPE: вызов чат-модели по роли, разбор структурированного ответа, расчёт стоимости прогона.
#   DEPENDS: M-CONFIG
#   LINKS: M-LLM, V-M-LLM
#   OUTPUTS: LLMResult с текстом, токенами, задержкой и ценой
#   SIDE_EFFECTS: исходящий HTTP к openrouter.ai
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   LLMResult - результат вызова: текст, модель, токены, задержка, цена
#   call - вызов модели по роли с обязательным таймаутом
#   parse_json_response - JSON из ответа модели, устойчиво к обрамлению markdown
#   PRICES - цены за миллион токенов для расчёта стоимости прогона
# END_MODULE_MAP

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from report_qa import config

__all__ = ["LLMResult", "call", "parse_json_response", "PRICES"]

# START_BLOCK_PRICES
# Цены OpenRouter на 2026-08-12, доллары за миллион токенов (вход, выход).
# Нужны для колонки «цена вопроса» в матрице замера: выбор архитектуры
# защищается таблицей, а таблица без стоимости неполна.
PRICES = {
    "anthropic/claude-opus-5": (10.0, 50.0),
    "anthropic/claude-opus-5-fast": (10.0, 50.0),
    "anthropic/claude-fable-5": (10.0, 50.0),
    "openai/gpt-5.5-pro": (30.0, 180.0),
    "google/gemini-2.5-flash": (0.3, 2.5),
}
# END_BLOCK_PRICES


# START_BLOCK_RESULT
@dataclass
class LLMResult:
    """Ответ модели вместе с ценой обращения к ней."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.prompt_tokens * price_in + self.completion_tokens * price_out) / 1e6
# END_BLOCK_RESULT


# START_BLOCK_CALL
def call(
    prompt: str,
    role: str = "answer",
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
    timeout: Optional[int] = None,
) -> LLMResult:
    """Вызов модели по роли.

    Таймаут обязателен и не имеет значения None: зависший HTTP без таймаута
    однажды уже подвесил фоновой воркер на сутки.
    """
    model = model or config.MODELS[role]
    timeout = timeout or config.HTTP_TIMEOUT

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    request = urllib.request.Request(
        config.OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {config.api_key()}",
            "Content-Type": "application/json",
        },
    )

    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"OpenRouter вернул {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenRouter недоступен: {exc.reason}") from exc
    latency = time.monotonic() - started

    choices = body.get("choices") or []
    if not choices:
        # Пустой ответ — это отказ, а не результат. Молча вернуть "" значит
        # записать в замер ноль вместо ошибки.
        raise RuntimeError(f"OpenRouter вернул ответ без choices: {str(body)[:300]}")

    usage = body.get("usage") or {}
    return LLMResult(
        text=choices[0].get("message", {}).get("content", ""),
        model=body.get("model", model),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        latency_s=round(latency, 2),
        raw=body,
    )
# END_BLOCK_CALL


# START_BLOCK_PARSE_JSON
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def parse_json_response(text: str) -> Any:
    """JSON из ответа модели.

    Модель охотно оборачивает JSON в markdown-заборчик и добавляет пояснение
    до и после. Разбираем и то, и другое, вместо того чтобы просить её так не делать.
    """
    if not text:
        raise ValueError("пустой ответ модели")

    fenced = _FENCE_RE.search(text)
    candidate = fenced.group(1) if fenced else text.strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Вырезаем крайние скобки: пояснения вокруг JSON встречаются регулярно.
    for opening, closing in (("[", "]"), ("{", "}")):
        start, end = candidate.find(opening), candidate.rfind(closing)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"не удалось разобрать JSON: {candidate[:200]}")
# END_BLOCK_PARSE_JSON

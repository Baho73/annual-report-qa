"""V-M-LLM: таймаут, учёт токенов, отказ вместо тихого пустого ответа."""

import json
import io
import urllib.error
import pytest

from report_qa import config, llm


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _payload(content="ответ", prompt_tokens=100, completion_tokens=10):
    return json.dumps({
        "model": "anthropic/claude-opus-5",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }).encode("utf-8")


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")


def test_call_passes_timeout(monkeypatch, key):
    """Каждый вызов уходит с таймаутом: зависший HTTP однажды подвесил воркер."""
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["timeout"] = timeout
        return _FakeResponse(_payload())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    llm.call("вопрос")
    assert seen["timeout"] == config.HTTP_TIMEOUT
    assert seen["timeout"] is not None


def test_call_returns_tokens_and_latency(monkeypatch, key):
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda r, timeout=None: _FakeResponse(_payload()))
    result = llm.call("вопрос")
    assert result.text == "ответ"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 10
    assert result.total_tokens == 110
    assert result.latency_s >= 0


def test_cost_computed_from_price_table(monkeypatch, key):
    """Цена вопроса нужна для матрицы замера, иначе таблица неполна."""
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda r, timeout=None: _FakeResponse(
                            _payload(prompt_tokens=1_000_000, completion_tokens=0)))
    result = llm.call("вопрос")
    assert result.cost_usd == pytest.approx(10.0)


def test_empty_choices_raise_instead_of_returning_blank(monkeypatch, key):
    """Пустой ответ — отказ, а не результат: иначе в замер попадёт ноль."""
    body = json.dumps({"choices": []}).encode("utf-8")
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda r, timeout=None: _FakeResponse(body))
    with pytest.raises(RuntimeError, match="без choices"):
        llm.call("вопрос")


def test_provider_error_is_explicit(monkeypatch, key):
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="недоступен"):
        llm.call("вопрос")


@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```\n[{"id": "s001"}]\n```', [{"id": "s001"}]),
    ('Вот ответ:\n{"a": 1}\nНадеюсь, помог.', {"a": 1}),
    ('Список: [1, 2, 3] — всё.', [1, 2, 3]),
])
def test_parse_json_survives_model_formatting(text, expected):
    """Модель оборачивает JSON в markdown и добавляет пояснения. Разбираем как есть."""
    assert llm.parse_json_response(text) == expected


def test_parse_json_rejects_garbage():
    with pytest.raises(ValueError):
        llm.parse_json_response("никакого JSON тут нет")

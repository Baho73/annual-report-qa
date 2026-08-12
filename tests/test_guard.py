"""V-M-GUARD: границы ответственности на инвестиционном вопросе.

Пятый вопрос задания — проверка не на знание, а на то, выдаст ли система
финансовый совет. Правильное поведение: факты выдать, вердикт не выдавать.
"""

import pytest

from report_qa.answer import is_advice_request, ADVICE_NOTICE


@pytest.mark.parametrize("question", [
    "Стоит ли инвестировать в эту компанию?",
    "Стоит ли покупать акции Яндекса?",
    "Стоит ли вкладываться?",
    "Рекомендуете покупать?",
    "Покупать ли акции?",
    "Выгодно ли инвестировать в компанию?",
    "Хорошее ли это вложение?",
    "Should I invest in this company?",
])
def test_advice_requests_detected(question):
    assert is_advice_request(question), f"не распознан запрос рекомендации: {question}"


@pytest.mark.parametrize("question", [
    "Какая была выручка компании в 2025 году?",
    "Какие направления росли быстрее остальных?",
    "Какие основные риски компания выделяет для бизнеса?",
    "Почему чистая прибыль выросла сильнее выручки?",
    "Какие факторы за и против инвестиций упоминает отчёт?",
    "Какая динамика долговой нагрузки?",
])
def test_factual_questions_not_guarded(question):
    """Вопрос про факторы отвечается полностью: ограничение не срабатывает."""
    assert not is_advice_request(question), f"ложное срабатывание: {question}"


def test_notice_explains_instead_of_refusing():
    """Отказ объясняет причину и не выглядит поломкой."""
    assert "лицензи" in ADVICE_NOTICE
    assert "за и против" in ADVICE_NOTICE
    assert "Решение остаётся за вами" in ADVICE_NOTICE


@pytest.mark.parametrize("verdict", ["покупайте", "продавайте", "рекомендую купить"])
def test_notice_contains_no_verdict(verdict):
    assert verdict not in ADVICE_NOTICE.lower()

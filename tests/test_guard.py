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


# --- Второй рубеж: вердикт в тексте ответа ---
# Проверка входа ловит намерение, проверка выхода — результат. Без второго
# рубежа достаточно перефразировать вопрос, чтобы совет вышел без пометки.

from report_qa.answer import has_verdict  # noqa: E402


@pytest.mark.parametrize("text", [
    "Рекомендую покупать акции компании",
    "Акции стоит купить на горизонте года",
    "Однозначно покупать",
    "Покупайте, компания растёт",
    "I recommend buying this stock",
])
def test_verdict_in_answer_detected(text):
    assert has_verdict(text), f"вердикт не пойман: {text}"


@pytest.mark.parametrize("text", [
    "Выручка выросла на 32% (стр. 86)",
    "Компания выделяет валютный и кредитный риск",
    "Стоит отметить рост сегмента городских сервисов",
    "Не рекомендую покупать без собственного анализа",
])
def test_factual_text_is_not_a_verdict(text):
    assert not has_verdict(text), f"ложное срабатывание: {text}"


def test_own_notice_does_not_trigger_detector():
    """Собственный блок о границах не должен поднимать флаг на себя."""
    assert not has_verdict(ADVICE_NOTICE)


def test_paraphrased_question_bypasses_input_check():
    """Честно фиксируем ограничение: список формулировок конечен.

    Именно поэтому второй рубеж работает по тексту ответа, а не по вопросу.
    """
    sneaky = "Как вы оцениваете перспективы акций компании?"
    assert not is_advice_request(sneaky)
    assert has_verdict("Перспективы отличные, рекомендую покупать")

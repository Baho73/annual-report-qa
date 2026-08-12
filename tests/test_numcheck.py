"""V-M-NUMCHECK: сверка чисел ответа с поданным контекстом.

Самый дешёвый приём в проекте: десять строк, никакой второй модели, а ловит
галлюцинацию ровно там, где она дороже всего стоит.
"""

import pytest

from report_qa.answer import check_numbers, numbers_in

CONTEXT = "выручка 1441.1 млрд, рост 35.76%, доля 55.83%, вклад 61.15%, убыток -8.3"


def test_number_present_in_context_passes():
    assert check_numbers("Выручка составила 1441,1 млрд руб.", CONTEXT) == []


def test_number_absent_from_context_is_flagged():
    """Выдуманное число обязано всплыть."""
    assert check_numbers("Выручка составила 9999,9 млрд руб.", CONTEXT) == ["9999.9"]


@pytest.mark.parametrize("written", ["1441,1", "1441.1", "1 441,1", "1 441,1"])
def test_format_does_not_matter(written):
    """Сравниваются значения, а не написание."""
    assert check_numbers(f"Выручка {written}", CONTEXT) == []


def test_rounding_is_not_invention():
    """Модель, написавшая 35,8 вместо 35,76, права и флага не заслуживает.

    Без этой поблажки проверка выдаёт шум на каждом ответе, и её перестают читать.
    """
    assert check_numbers("Рост 35,8%, доля 55,8%, вклад 61,2%", CONTEXT) == []


def test_years_are_not_numbers():
    assert check_numbers("В 2025 году против 2024 года", CONTEXT) == []


def test_page_citations_are_not_numbers():
    """Ссылка на страницу — не данные, иначе каждая цитата давала бы флаг."""
    assert check_numbers("Выручка 1441,1 (стр. 777)", CONTEXT) == []


def test_negative_values_handled():
    assert check_numbers("Убыток составил -8,3", CONTEXT) == []


def test_empty_context_flags_everything():
    """Если контекста нет, доверять нечему."""
    assert check_numbers("Выручка 1441,1", "") == ["1441.1"]


def test_numbers_in_normalizes():
    assert numbers_in("1 441,1 и 1441.10") == {"1441.1"}

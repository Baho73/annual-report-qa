"""V-M-NUM: нормализация чисел финансовой отчётности.

Краевые случаи взяты из реального документа: скобки как минус, неразрывный
пробел как разделитель тысяч, единица в шапке, сноски-звёздочки.
"""

import pytest

from report_qa.parse import parse_number, extract_unit, parse_cell


@pytest.mark.parametrize("raw,expected", [
    ("(1 234,5)", -1234.5),          # скобки означают минус
    ("(1 234)", -1234.0),
    ("1 234 567", 1234567.0),        # обычные пробелы
    ("1 441,1", 1441.1),        # неразрывный пробел
    ("1 441,1", 1441.1),        # узкий неразрывный
    ("1 441,1", 1441.1),
    ("12,3", 12.3),
    ("−8,3", -8.3),                  # U+2212 минус
    ("–5,0", -5.0),                  # en dash как минус
    ("-0,4", -0.4),
    ("0,58", 0.58),
    ("32", 32.0),
    ("1 630,9", 1630.9),
])
def test_parse_number_values(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "-", "–", "—", "н/д", "N/A", "...", None, "   "])
def test_empty_tokens_produce_no_record(raw):
    """Прочерк и «н/д» записи не создают: пустая ячейка не ноль."""
    assert parse_number(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("1 441,1*", 1441.1),            # сноска-звёздочка
    ("269,7¹", 269.7),               # надстрочный индекс
    ("47,7†", 47.7),
])
def test_footnotes_stripped(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


def test_unit_stays_out_of_value():
    """Единица измерения не попадает в число."""
    assert parse_number("1 441,1 млрд руб.") == pytest.approx(1441.1)
    assert parse_number("12,3%") == pytest.approx(12.3)


@pytest.mark.parametrize("source,unit", [
    ("Выручка, млрд руб.", "млрд_руб"),
    ("Выручка, млн руб.", "млн_руб"),
    ("Рентабельность, %", "%"),
    ("Изменение, п.п.", "п.п."),
    ("Количество, шт", "шт"),
    ("Просто заголовок", None),
])
def test_extract_unit_from_header(source, unit):
    assert extract_unit(source) == unit


def test_unit_nearest_source_wins():
    """Ближайший к числу источник важнее дальнего заголовка."""
    assert extract_unit("12,3%", "Выручка, млрд руб.") == "%"


def test_parse_cell_pairs_value_and_unit():
    value, unit = parse_cell("1 441,1", "Выручка, млрд руб.")
    assert value == pytest.approx(1441.1)
    assert unit == "млрд_руб"


def test_parse_cell_empty_gives_nothing():
    assert parse_cell("—", "Выручка, млрд руб.") == (None, None)


def test_thousands_dot_separator():
    """«1.234.567» — точки как разделители тысяч, а не десятичные."""
    assert parse_number("1.234.567") == pytest.approx(1234567.0)

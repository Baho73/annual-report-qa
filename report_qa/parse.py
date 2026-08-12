"""M-NUM / M-PARSE / M-TABLES / M-AGG: разбор документа и подготовка данных.

MODULE_CONTRACT:
    PURPOSE: превратить PDF в смысловые разделы и числа, пригодные для вычислений.
    SCOPE:   parse_number, extract_unit (M-NUM); build_sections (M-PARSE);
             агрегаты и контрольные суммы (M-AGG).
    DEPENDS: M-CONFIG.
"""

import re
import unicodedata
from typing import Optional, Tuple

# START_BLOCK_NUM_NORMALIZE
# Пробелы, которыми в отчётности разделяют тысячи: обычный, неразрывный,
# узкий неразрывный, тонкий.
_SPACES = "     "
_SPACE_RE = re.compile(f"[{_SPACES}]")

# Значения, которые записи не порождают.
_EMPTY_TOKENS = {"", "-", "–", "—", "н/д", "нд", "n/a", "na", "—", "–", "..."}

# Сноски: звёздочка, крестик, надстрочные цифры в конце значения.
_FOOTNOTE_RE = re.compile(r"[\*†‡¹²³⁰-₟]+$")

_UNIT_PATTERNS = [
    (re.compile(r"млрд", re.I), "млрд_руб"),
    (re.compile(r"млн", re.I), "млн_руб"),
    (re.compile(r"тыс", re.I), "тыс_руб"),
    (re.compile(r"%|проц", re.I), "%"),
    (re.compile(r"\bшт\b|штук", re.I), "шт"),
    (re.compile(r"п\.\s*п\.|процентн\w+ пункт", re.I), "п.п."),
]


def parse_number(raw: object) -> Optional[float]:
    """Число из ячейки финансовой таблицы.

    Скобки означают минус: «(1 234,5)» это -1234.5, а не 1234.5. Без этого
    правила знак теряется молча и вся последующая арифметика уезжает.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)

    # Сноски отрезаются ДО NFKC: нормализация превращает надстрочную «¹»
    # в обычную единицу, и «269,7¹» стало бы 269.71.
    s = _FOOTNOTE_RE.sub("", str(raw).strip()).strip()
    s = unicodedata.normalize("NFKC", s).strip()
    if s.lower() in _EMPTY_TOKENS:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    if s.startswith(("−", "–", "—")):  # минус, en dash, em dash
        negative = True
        s = s[1:].strip()
    elif s.startswith("-"):
        negative = True
        s = s[1:].strip()

    # Единицу и знак процента из значения убираем: они живут в поле unit.
    s = re.sub(r"(млрд|млн|тыс)\.?\s*(руб\w*)?\.?", "", s, flags=re.I)
    s = s.replace("%", "")
    s = _SPACE_RE.sub("", s).strip()

    if not s or s.lower() in _EMPTY_TOKENS:
        return None

    # После удаления разделителей тысяч десятичным остаётся запятая.
    s = s.replace(",", ".")
    # Хвостовая точка от конца предложения.
    s = s.rstrip(".")
    if s.count(".") > 1:
        # Несколько точек: либо все разделители тысяч («1.234.567»), либо
        # тысячи плюс десятичная («1.234.5»). Различаем по длине последней группы.
        head, _, tail = s.rpartition(".")
        if len(tail) == 3:
            s = (head + tail).replace(".", "")
        else:
            s = head.replace(".", "") + "." + tail

    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def extract_unit(*sources: object) -> Optional[str]:
    """Единица измерения из шапки таблицы, подписи оси или самой ячейки.

    Единица в отчётности живёт в заголовке, а не рядом с числом, поэтому
    источников несколько и порядок важен: ближайший к числу выигрывает.
    """
    for src in sources:
        if not src:
            continue
        text = str(src)
        for pattern, unit in _UNIT_PATTERNS:
            if pattern.search(text):
                return unit
    return None


def parse_cell(raw: object, *unit_sources: object) -> Tuple[Optional[float], Optional[str]]:
    """Значение и единица одной ячейки. Пустая ячейка даёт (None, None)."""
    value = parse_number(raw)
    if value is None:
        return None, None
    return value, extract_unit(raw, *unit_sources)
# END_BLOCK_NUM_NORMALIZE

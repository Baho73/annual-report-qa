"""M-NUM / M-PARSE / M-TABLES / M-AGG: разбор документа и подготовка данных.

MODULE_CONTRACT:
    PURPOSE: превратить PDF в смысловые разделы и числа, пригодные для вычислений.
    SCOPE:   parse_number, extract_unit (M-NUM); build_sections (M-PARSE);
             агрегаты и контрольные суммы (M-AGG).
    DEPENDS: M-CONFIG.
"""

import json
import re
import unicodedata
from typing import List, Optional, Tuple

from report_qa import config

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


# START_BLOCK_SECTIONS
def _slug(title: str, index: int) -> str:
    """Устойчивый идентификатор раздела: латиница по возможности, иначе номер."""
    base = re.sub(r"[^\w]+", "-", title.strip().lower(), flags=re.U).strip("-")
    return f"s{index:03d}-{base[:40]}" if base else f"s{index:03d}"


def build_sections(pdf_path=None) -> List[dict]:
    """Разделы документа по встроенным закладкам.

    Закладки проставлены автором отчёта — это готовая смысловая разметка, и
    парсер оглавления писать не нужно. Единица выборки для роутера — раздел
    с границами страниц, поэтому таблица внутри него не рвётся.
    """
    import fitz  # локальный импорт: тестам нормализации fitz не нужен

    pdf_path = pdf_path or config.PDF_PATH
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    pages = [p.get_text() for p in doc]
    total = doc.page_count

    if not toc:
        # Фолбэк для PDF без закладок: весь документ одним разделом.
        # ponytail: эвристику по кеглю заголовков добавлять, когда встретится
        # реальный документ без закладок.
        return [{
            "id": "s001-document", "title": "Документ", "level": 1,
            "page_from": 1, "page_to": total,
            "text": "\n".join(pages),
        }]

    sections = []
    for i, (level, title, page) in enumerate(toc):
        # Конец раздела — страница перед следующей закладкой того же или
        # более высокого уровня.
        page_to = total
        for next_level, _, next_page in toc[i + 1:]:
            if next_level <= level:
                page_to = max(page, next_page - 1)
                break
        sections.append({
            "id": _slug(title, i + 1),
            "title": title.strip(),
            "level": level,
            "page_from": page,
            "page_to": page_to,
            "text": "\n".join(pages[page - 1:page_to]),
        })
    doc.close()
    return sections


def save_sections(sections: List[dict], path=None) -> None:
    path = path or config.SECTIONS_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=1)


def load_sections(path=None) -> List[dict]:
    path = path or config.SECTIONS_JSON
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def toc_outline(sections: List[dict], max_level: int = 2) -> str:
    """Оглавление для роутера: заголовки со страницами, без текста.

    Роутеру подаётся 2-3k токенов вместо 175k, поэтому платить за интеллект
    на этом шаге не за что.
    """
    lines = []
    for s in sections:
        if s["level"] <= max_level:
            indent = "  " * (s["level"] - 1)
            lines.append(f'{indent}{s["id"]} | {s["title"]} | стр. {s["page_from"]}-{s["page_to"]}')
    return "\n".join(lines)
# END_BLOCK_SECTIONS


if __name__ == "__main__":
    secs = build_sections()
    save_sections(secs)
    top = [s for s in secs if s["level"] == 1]
    print(f"разделов: {len(secs)} (уровень 1: {len(top)})")
    print(f"записано: {config.SECTIONS_JSON}")

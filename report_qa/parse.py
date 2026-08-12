"""M-NUM / M-PARSE / M-AGG: разбор документа и подготовка данных."""

# FILE: report_qa/parse.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: превратить PDF в смысловые разделы и числа, пригодные для вычислений кодом.
#   SCOPE: нормализация чисел финотчётности; разделы по встроенным закладкам; агрегаты и контрольные суммы.
#   DEPENDS: M-CONFIG
#   LINKS: M-NUM, M-PARSE, M-AGG, V-M-NUM, V-M-PARSE, V-M-AGG
#   INPUTS: data/yandex_annual_report_2025.pdf, data/tables_merged.json
#   OUTPUTS: data/sections.json, data/aggregates.json
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   parse_number - число из ячейки: скобки как минус, четыре вида пробелов, сноски до NFKC
#   extract_unit - единица измерения из шапки таблицы или подписи оси
#   parse_cell - пара значение и единица; пустая ячейка даёт (None, None)
#   build_sections - разделы по 178 встроенным закладкам документа
#   save_sections - запись разделов в data/sections.json
#   load_sections - чтение разделов из артефакта
#   toc_outline - оглавление для роутера, 2-3k токенов вместо 175k
#   load_tables - чтение чисел длинного формата с провенансом
#   total_revenue - консолидированная выручка периода, выбор по доверию к источнику
#   compute_aggregates - приросты, доли, вклад в прирост; арифметика в коде, не в модели
#   checksum_segments - сумма блоков против итога, детектор собственной ошибки разбора
#   save_aggregates - запись агрегатов и контрольной суммы в data/aggregates.json
#   TOP_SEGMENTS - блоки верхнего уровня сегментной отчётности
# END_MODULE_MAP

import json
import re
import unicodedata
from typing import List, Optional, Tuple

from report_qa import config

__all__ = [
    "parse_number", "extract_unit", "parse_cell",
    "build_sections", "save_sections", "load_sections", "toc_outline",
    "load_tables", "total_revenue", "compute_aggregates", "checksum_segments",
    "save_aggregates", "TOP_SEGMENTS",
]

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


# START_BLOCK_AGGREGATES
# Блоки верхнего уровня сегментной отчётности: сумма их выручки плюс
# межсегментные расчёты даёт консолидированный итог.
TOP_SEGMENTS = [
    "Поисковые сервисы и ИИ",
    "Городские сервисы",
    "Персональные сервисы",
    "Б2Б Тех",
    "Автономные технологии",
    "Прочие сервисы и инициативы",
]

_REVENUE_TOTAL_NAMES = {"общая выручка", "выручка", "консолидированная выручка"}


def load_tables(path=None) -> List[dict]:
    path = path or config.TABLES_JSON
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line and line not in "[]":
                out.append(json.loads(line))
    return out


def _pick(records, metric_sub, segment=None, period=None):
    """Значение по подстроке метрики, сегменту и периоду. None если нет."""
    for r in records:
        if metric_sub.lower() not in str(r.get("m", "")).lower():
            continue
        if segment is not None and r.get("s") != segment:
            continue
        if segment is None and r.get("s"):
            continue
        if period is not None and str(r.get("p")) != str(period):
            continue
        if r.get("v") is not None:
            return r
    return None


def _trust(rec: dict) -> tuple:
    """Ключ доверия к записи: подтверждённая двумя путями выигрывает.

    Дальше — точность: 1441.1 из финансового раздела предпочтительнее
    округлённого 1441.0 из обзорной врезки.
    """
    confirmed = 1 if (rec.get("confirmed") or rec.get("src") == "both") else 0
    value = rec.get("v") or 0
    precision = 1 if abs(value - round(value)) > 1e-9 else 0
    return (confirmed, precision, -(rec.get("pg") or 999))


def total_revenue(records, period) -> Optional[dict]:
    """Консолидированная выручка периода.

    Кандидатов в документе несколько (обзорная врезка, сегментная таблица,
    финансовый раздел). Берём наиболее доверенный, а не первый попавшийся.
    """
    candidates = []
    for name in _REVENUE_TOTAL_NAMES:
        for rec in records:
            if str(rec.get("m", "")).strip().lower() != name:
                continue
            if rec.get("s") or str(rec.get("p")) != str(period):
                continue
            if rec.get("v") is None or rec.get("u") != "млрд_руб":
                continue
            candidates.append(rec)
    if not candidates:
        return None
    return max(candidates, key=_trust)


def compute_aggregates(records=None, cur="2025", prev="2024") -> dict:
    """Приросты, доли и вклад в прирост — считает код, не модель.

    Вклад в прирост отвечает на вопрос, почему прибыль выросла сильнее
    выручки: там нужна раскладка по драйверам, а не одно число.
    ponytail: чистый Python вместо pandas — 868 записей, зависимость не окупается.
    """
    records = records if records is not None else load_tables()
    tot_cur = total_revenue(records, cur)
    tot_prev = total_revenue(records, prev)
    total_growth = None
    if tot_cur and tot_prev:
        total_growth = tot_cur["v"] - tot_prev["v"]

    segments = []
    for seg in TOP_SEGMENTS:
        a = _pick(records, "выручк", segment=seg, period=cur)
        b = _pick(records, "выручк", segment=seg, period=prev)
        if not a:
            continue
        row = {
            "segment": seg,
            "period": cur,
            "value": a["v"],
            "unit": a.get("u"),
            "page": a.get("pg"),
            "prev": b["v"] if b else None,
        }
        if b and b["v"]:
            row["yoy_abs"] = round(a["v"] - b["v"], 3)
            row["yoy_pct"] = round((a["v"] - b["v"]) / abs(b["v"]) * 100, 2)
            if total_growth:
                row["contrib_growth_pct"] = round((a["v"] - b["v"]) / total_growth * 100, 2)
        if tot_cur and tot_cur["v"]:
            row["share_pct"] = round(a["v"] / tot_cur["v"] * 100, 2)
        segments.append(row)

    segments.sort(key=lambda r: r.get("yoy_pct", float("-inf")), reverse=True)
    return {
        "period": cur,
        "prev_period": prev,
        "total_revenue": tot_cur["v"] if tot_cur else None,
        "total_revenue_page": tot_cur.get("pg") if tot_cur else None,
        "total_revenue_prev": tot_prev["v"] if tot_prev else None,
        "total_growth_abs": round(total_growth, 3) if total_growth else None,
        "segments": segments,
    }


def checksum_segments(records=None, period="2025") -> dict:
    """Сумма блоков против консолидированного итога.

    Расхождение выше порога означает потерянную строку или неразобранный знак.
    Без этой сверки ошибка разбора становится уверенным враньём в ответе.
    Известный результат: 1630.9 против 1441.1 (13.17%), причина в сносках
    стр. 21 и 87 — блоковая выручка дана до коррекции на межсегментные расчёты.
    """
    records = records if records is not None else load_tables()
    parts, seen = [], set()
    for r in records:
        seg = r.get("s")
        if seg in TOP_SEGMENTS and str(r.get("p")) == period and r.get("v") is not None:
            if "выручк" in str(r.get("m", "")).lower() and seg not in seen:
                seen.add(seg)
                parts.append({"segment": seg, "value": r["v"], "page": r.get("pg")})

    inter = [r["v"] for r in records
             if str(r.get("p")) == period and r.get("v") is not None
             and "ежсегмент" in f'{r.get("m","")} {r.get("s","")}']
    # Межсегментные расчёты встречаются и как отдельные строки блоков,
    # и как общая корректировка. Берём корректировку по модулю один раз.
    correction = -abs(max(inter, key=abs)) if inter else 0.0

    tot = total_revenue(records, period)
    raw_sum = round(sum(p["value"] for p in parts), 3)
    adjusted = round(raw_sum + correction, 3)
    total = tot["v"] if tot else None

    result = {
        "check": "segments_vs_total",
        "period": period,
        "parts": parts,
        "sum_raw": raw_sum,
        "intersegment_correction": round(correction, 3),
        "sum_adjusted": adjusted,
        "total": total,
    }
    if total:
        result["delta_raw_pct"] = round((raw_sum - total) / total * 100, 3)
        result["delta_pct"] = round(abs(adjusted - total) / total * 100, 3)
        result["ok"] = result["delta_pct"] <= config.THRESHOLDS["checksum_delta_pct"]
    else:
        result["ok"] = False
        result["reason"] = "консолидированный итог не найден в данных"
    return result


def save_aggregates(path=None) -> dict:
    records = load_tables()
    payload = {
        "aggregates": compute_aggregates(records),
        "checksum": checksum_segments(records),
    }
    path = path or config.AGGREGATES_JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload
# END_BLOCK_AGGREGATES

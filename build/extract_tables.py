# -*- coding: utf-8 -*-
"""
Извлечение числовых таблиц из годового отчёта МКПАО «Яндекс» за 2025 год.

Три источника данных в PDF:
  A. GRID  — настоящие таблицы с сеткой (pdfplumber / координаты fitz).
  B. VEC   — графики, у которых подписи значений лежат в текстовом слое
             (извлекаются по координатам: тики года + ближайшая по X подпись).
  C. IMG   — графики, вставленные РАСТРОМ (текстового слоя нет вообще).
             Значения сняты визуально с рендера страницы и записаны литералами;
             каждый такой блок помечен в REPORT_SOURCES как 'image'.

Выход: data/tables.json (JSON Lines), запись = одна ячейка:
  {"t","m","s","p","v","u","pg"}
"""
import json
import os
import re
import sys

import fitz
import pdfplumber

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"
OUT = r"D:\Python\annual-report-qa\data\tables.json"

RECORDS = []
SOURCES = {}   # table_id -> ("grid"|"vec"|"img", pages)

# ----------------------------------------------------------------------------
# Нормализация чисел
# ----------------------------------------------------------------------------
SPACES = "\u00a0\u202f\u2009\u2007\u2060 "
DASHES = "\u2212\u2013\u2014\u2012"


def norm_num(s):
    """'(1 234,5)' -> -1234.5 ; '19,5' -> 19.5 ; '–' / 'н/д' / '' -> None."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    # отрезаем хвостовые сноски-звёздочки
    s = s.rstrip("*")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    for ch in SPACES:
        s = s.replace(ch, "")
    for ch in DASHES:
        s = s.replace(ch, "-")
    s = s.rstrip("%")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    s = s.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    v = float(s)
    if v == int(v):
        v = int(v)
    return -v if neg else v


def emit(t, m, s, p, v, u, pg):
    if v is None:
        return
    RECORDS.append({"t": t, "m": m, "s": s, "p": p, "v": v, "u": u, "pg": pg})


# ----------------------------------------------------------------------------
# Работа со словами fitz
# ----------------------------------------------------------------------------
doc = fitz.open(PDF)


def merged_words(pno, gap=3.2):
    """Слова страницы, склеенные по базовой линии (чтобы '1' + '441,1' -> '1441,1').
    Возвращает список (x0, y0, x1, y1, text)."""
    ws = doc.load_page(pno - 1).get_text("words")
    ws.sort(key=lambda w: (round(w[1], 1), w[0]))
    out = []
    for w in ws:
        if out:
            px0, py0, px1, py1, ptxt = out[-1]
            if abs(w[1] - py0) < 1.2 and 0 <= (w[0] - px1) < gap:
                out[-1] = (px0, py0, max(px1, w[2]), max(py1, w[3]), ptxt + w[4])
                continue
        out.append((w[0], w[1], w[2], w[3], w[4]))
    return out


def stream_values(pno, y_lo, y_hi, n, allow_pct=True, exclude=()):
    """Числовые подписи в порядке потока контента PDF (порядок серий графика)."""
    ws = doc.load_page(pno - 1).get_text("words")
    nums = [w for w in ws if y_lo <= w[1] <= y_hi and is_value(w[4], allow_pct)
            and w[4] not in exclude]
    if len(nums) != n:
        raise AssertionError(f"p{pno} stream [{y_lo},{y_hi}]: чисел {len(nums)}, ожидали {n} -> "
                             f"{[w[4] for w in nums]}")
    return [norm_num(w[4]) for w in nums]


VALUE_RE = re.compile(r"^[-\u2212\u2013(]?\d[\d" + SPACES + r"]*(?:[,.]\d+)?\)?$")


def is_value(txt, allow_pct=False):
    t = txt.strip()
    if not allow_pct and t.endswith("%"):
        return False
    if allow_pct:
        t = t.rstrip("%")
    if t.startswith("+"):
        return False           # +25% / +2,6 п. п. — это подписи роста, не значения
    return bool(VALUE_RE.match(t))


def tick_chart(pno, tick_y, labels, y_lo, y_hi, ticks=("2022", "2023", "2024", "2025"),
               allow_pct=False, tol=3.0, max_dx=22.0):
    """Столбчатый график: находит тики года на строке tick_y, для каждого тика
    подбирает ближайшую по X числовую подпись из полосы [y_lo, y_hi].
    labels — список той же длины, что и тики (слева направо).
    Возвращает [(label, tick_text, value)]."""
    ws = merged_words(pno)
    tk = [w for w in ws if w[4] in ticks and abs(w[1] - tick_y) < tol]
    tk.sort(key=lambda w: w[0])
    if len(tk) != len(labels):
        raise AssertionError(
            f"p{pno} tick_y={tick_y}: тиков {len(tk)}, ожидали {len(labels)} -> {[t[4] for t in tk]}")
    nums = [w for w in ws if y_lo <= w[1] <= y_hi and is_value(w[4], allow_pct)
            and not (w[4] in ticks and abs(w[1] - tick_y) < tol)]
    used = set()
    res = []
    for lab, t in zip(labels, tk):
        cx = (t[0] + t[2]) / 2
        best, bestd = None, 1e9
        for i, n in enumerate(nums):
            if i in used:
                continue
            d = abs((n[0] + n[2]) / 2 - cx)
            if d < bestd:
                best, bestd = i, d
        if best is None or bestd > max_dx:
            raise AssertionError(f"p{pno} тик {t[4]} @x={cx:.0f}: подпись не найдена (d={bestd:.1f})")
        used.add(best)
        res.append((lab, t[4], norm_num(nums[best][4])))
    return res


def ordered_values(pno, y_lo, y_hi, n, allow_pct=True, x_lo=-1e9, x_hi=1e9, sort_by="y"):
    """Числовые подписи полосы [y_lo,y_hi]; sort_by='y' — порядок чтения, 'x' — слева направо."""
    ws = merged_words(pno)
    nums = [w for w in ws if y_lo <= w[1] <= y_hi and x_lo <= w[0] <= x_hi
            and is_value(w[4], allow_pct)]
    if sort_by == "x":
        nums.sort(key=lambda w: w[0])
    else:
        nums.sort(key=lambda w: (round(w[1], 1), w[0]))
    if len(nums) != n:
        raise AssertionError(f"p{pno} [{y_lo},{y_hi}]: чисел {len(nums)}, ожидали {n} -> "
                             f"{[w[4] for w in nums]}")
    return [norm_num(w[4]) for w in nums]


# ============================================================================
# A. GRID-ТАБЛИЦЫ
# ============================================================================

# --- A1. Основные финансовые показатели, стр. 86 -----------------------------
def t_main_financials():
    tid, pg = "main_financials", 86
    SOURCES[tid] = ("grid", [pg])
    ws = merged_words(pg)                       # склеенные — для чисел
    raw = doc.load_page(pg - 1).get_text("words")  # исходные — для текстовых подписей
    col_2024 = [w for w in ws if 300 < w[0] < 400 and 240 < w[1] < 540 and is_value(w[4])]
    col_2024.sort(key=lambda w: w[1])
    assert len(col_2024) == 7, [w[4] for w in col_2024]
    for row in col_2024:
        y = row[1]
        label = " ".join(w[4] for w in sorted(
            [w for w in raw if w[0] < 235 and abs(w[1] - y) < 21], key=lambda w: (w[1], w[0])))
        unit_txt = " ".join(w[4] for w in sorted(
            [w for w in raw if 235 <= w[0] < 300 and abs(w[1] - y) < 21], key=lambda w: (w[1], w[0])))
        u = "%" if unit_txt.strip() == "%" else "млрд_руб"
        v25 = [w for w in ws if 400 < w[0] < 470 and abs(w[1] - y) < 8 and is_value(w[4])]
        chg_txt = " ".join(w[4] for w in sorted(
            [w for w in raw if w[0] > 470 and abs(w[1] - y) < 8], key=lambda w: w[0]))
        emit(tid, label, None, "2024", norm_num(row[4]), u, pg)
        if v25:
            emit(tid, label, None, "2025", norm_num(v25[0][4]), u, pg)
        if "Неприменимо" in chg_txt:
            pass
        elif "п." in chg_txt:
            emit(tid, label + " (изменение г/г)", None, "2025",
                 norm_num(chg_txt.replace("п.", "").strip()), "п.п.", pg)
        elif chg_txt:
            emit(tid, label + " (изменение г/г)", None, "2025",
                 norm_num(chg_txt.replace(" ", "")), "%", pg)


# --- A2..A8: таблицы, которые нормально берёт pdfplumber ---------------------
def plumber_rows(pno, idx):
    with pdfplumber.open(PDF) as pdf:
        t = pdf.pages[pno - 1].find_tables()[idx]
        data = t.extract()
    rows = []
    for r in data:
        cells = [" ".join(c.split()) for c in r if c and c.split()]
        if cells:
            rows.append(cells)
    return rows


def t_corp_code():
    tid = "corp_code_compliance"
    SOURCES[tid] = ("grid", [105, 106])
    cols = [("Всего вопросов", None), ("Соблюдаются", "2025"), ("Соблюдаются", "2024"),
            ("Частично соблюдаются", "2025"), ("Частично соблюдаются", "2024"),
            ("Не соблюдаются", "2025"), ("Не соблюдаются", "2024")]
    for pg in (105, 106):
        for row in plumber_rows(pg, 0):
            if len(row) < 4 or norm_num(row[1]) is None and "Доля" not in row[0]:
                continue
            name = row[0]
            vals = row[1:]
            if name.startswith("Доля выполнения"):
                for (metric, per), raw in zip(cols[1:], vals):
                    emit(tid, "Доля выполнения принципов Кодекса — " + metric, None,
                         per, norm_num(raw), "%", pg)
                continue
            if len(vals) != 7:
                continue
            for (metric, per), raw in zip(cols, vals):
                v = norm_num(raw)
                if v is None:
                    continue
                emit(tid, metric, name, per if per else "2025", v, "шт", pg)


def t_committees():
    tid, pg = "board_committees_composition", 112
    SOURCES[tid] = ("grid", [pg])
    cols = ["Независимые директора", "Исполнительные директора", "Неисполнительные директора"]
    for row in plumber_rows(pg, 0):
        if not row[0].startswith("Комитет") or len(row) != 4:
            continue
        for m, raw in zip(cols, row[1:]):
            emit(tid, m, row[0], "2025", norm_num(raw), "шт", pg)


def t_board_pay():
    tid, pg = "board_remuneration", 116
    SOURCES[tid] = ("grid", [pg])
    cols = ["Базовое вознаграждение", "Дополнительное вознаграждение",
            "Компенсация расходов", "Всего"]
    for row in plumber_rows(pg, 0):
        if row[0] not in ("2024", "2025") or len(row) != 5:
            continue
        for m, raw in zip(cols, row[1:]):
            emit(tid, m, None, row[0], norm_num(raw), "млн_руб", pg)


def t_share_issues():
    tid, pg = "share_issues_2025", 128
    SOURCES[tid] = ("grid", [pg])
    for row in plumber_rows(pg, 0):
        if not re.match(r"\d{2}\.\d{2}\.2025", row[0]) or len(row) < 2:
            continue
        emit(tid, "Количество размещённых акций", None, row[0], norm_num(row[1]), "шт", pg)


def t_share_trading():
    tid, pg = "share_trading_2025", 129
    SOURCES[tid] = ("grid", [pg])
    for row in plumber_rows(pg, 0):
        if len(row) != 2 or norm_num(row[1]) is None:
            continue
        emit(tid, row[0], None, "2025", norm_num(row[1]), "руб", pg)


def t_analysts():
    tid, pg = "analyst_coverage_2025", 129
    SOURCES[tid] = ("grid", [pg])
    for row in plumber_rows(pg, 1):
        if len(row) != 3 or not row[1].startswith("«"):
            continue
        emit(tid, "Прогноз цены акции", row[0], "2025", norm_num(row[2]), "руб", pg)


def t_dividends():
    tid, pg = "dividends_history", 131
    SOURCES[tid] = ("grid", [pg])
    PER = {"2024": "2024",
           "по результатам первого полугодия 2024 года": "1п2024",
           "по результатам 2024 года": "2024_итоговый",
           "по результатам первого полугодия 2025 года": "1п2025"}
    for row in plumber_rows(pg, 0):
        if len(row) != 3 or row[0] not in PER:
            continue
        period = PER[row[0]]
        emit(tid, "Общая сумма дивидендов", None, period, norm_num(row[1]), "руб", pg)
        emit(tid, "Дивиденд на одну акцию", None, period, norm_num(row[2]), "руб", pg)


# ============================================================================
# B. VEC-ГРАФИКИ (подписи в текстовом слое)
# ============================================================================

def t_key_metrics_3y():
    """стр. 12-14: выручка / EBITDA / скорр. ЧП / рентабельность / опер. метрики."""
    specs = [
        ("key_financials_3y", 12, "Выручка", None, "млрд_руб", 706.7, 540, 700),
        ("key_financials_3y", 13, "Скорректированный показатель EBITDA", None, "млрд_руб", 271.8, 100, 265),
        ("key_financials_3y", 13, "Скорректированная чистая прибыль", None, "млрд_руб", 521.8, 360, 515),
        ("key_financials_3y", 13, "Рентабельность по скорректированной EBITDA", None, "%", 742.9, 620, 736),
        ("key_operational_3y", 14, "Доля Поиска Яндекса", None, "%", 263.3, 118, 257),
        ("key_operational_3y", 14, "MAU Городских сервисов", None, "млн", 497.9, 345, 491),
        ("key_operational_3y", 14, "Число подписчиков Яндекс Плюса", None, "млн", 744.7, 595, 738),
    ]
    for tid, pg, m, s, u, ty, ylo, yhi in specs:
        SOURCES.setdefault(tid, ("vec", []))
        if pg not in SOURCES[tid][1]:
            SOURCES[tid][1].append(pg)
        for _lab, year, v in tick_chart(pg, ty, ["2023", "2024", "2025"], ylo, yhi):
            emit(tid, m, s, year, v, u, pg)


def t_revenue_distribution_21():
    """стр. 21: распределение выручки группы за 2025 (текстовый блок)."""
    tid, pg = "revenue_distribution_2025", 21
    SOURCES[tid] = ("vec", [pg])
    SEG = {"Городские сервисы", "Поисковые сервисы и ИИ", "Персональные сервисы",
           "Б2Б Тех", "Автономные технологии", "Прочие сервисы и инициативы"}
    lines = [l.strip() for l in doc.load_page(pg - 1).get_text("text").split("\n")]
    for i, ln in enumerate(lines):
        mm = re.match(r"^([\d" + SPACES + r"]+,\d+)\s+млрд рублей$", ln)
        if not mm:
            continue
        lab, j = [], i - 1
        while j >= 0 and len(lab) < 2:
            cur = lines[j]
            j -= 1
            if not cur:
                continue
            if "млрд рублей" in cur or "% от выручки" in cur:
                break
            lab.insert(0, cur)
            if cur.endswith(":"):
                break
        name = re.sub(r"\d+$", "", " ".join(lab).rstrip(":").strip()).strip()
        v = norm_num(mm.group(1))
        if name in SEG:
            emit(tid, "Выручка", name, "2025", v, "млрд_руб", pg)
        elif name.startswith("Выручка всего"):
            emit(tid, "Выручка (консолидированная)", None, "2025", v, "млрд_руб", pg)
        else:
            emit(tid, name, None, "2025", v, "млрд_руб", pg)
    emit(tid, "CAPEX, % от выручки", None, "2025", 10.1, "%", pg)
    emit(tid, "Коррекция на межсегментные расчёты", None, "2025", -189.7, "млрд_руб", pg)


def t_search_market():
    """стр. 26: доли на рынке поиска; стр. 30: доля Яндекса 3 года (все/мобильные)."""
    tid = "search_market_share"
    SOURCES[tid] = ("vec", [26, 30])
    vals = stream_values(26, 230, 370, 3)
    for s, v in zip(["Яндекс", "Google", "Прочие системы (Mail.ru, Rambler и другие)"], vals):
        emit(tid, "Доля на российском поисковом рынке", s, "2025", v, "%", 26)
    v_all = stream_values(30, 125, 250, 3, exclude=("2023", "2024", "2025"))
    for p, v in zip(["2025", "2024", "2023"], v_all):
        emit(tid, "Доля Яндекса на российском поисковом рынке", "все устройства", p, v, "%", 30)
    v_mob = stream_values(30, 285, 420, 3, exclude=("2023", "2024", "2025"))
    for p, v in zip(["2025", "2024", "2023"], v_mob):
        emit(tid, "Доля Яндекса на российском поисковом рынке", "мобильные устройства", p, v, "%", 30)


def t_plus_quarterly():
    tid, pg = "plus_subscribers_quarterly", 51
    SOURCES[tid] = ("vec", [pg])
    periods = ["4кв2023", "1кв2024", "2кв2024", "3кв2024", "4кв2024",
               "1кв2025", "2кв2025", "3кв2025", "4кв2025"]
    vals = ordered_values(pg, 245, 312, 9, allow_pct=False, sort_by="x")
    for p, v in zip(periods, vals):
        emit(tid, "Число подписчиков Яндекс Плюса", None, p, v, "млн", pg)


def t_city_breakdown():
    """стр. 92: выручка и скорр. EBITDA Городских сервисов по подсегментам."""
    tid = "city_services_breakdown"
    SOURCES[tid] = ("vec", [92, 93])
    subs_rev = ["Райдтех", "Райдтех", "Сервисы электронной коммерции",
                "Сервисы электронной коммерции", "Доставка и другие O2O-сервисы",
                "Доставка и другие O2O-сервисы",
                "Межсегментные расчёты (Городские сервисы)",
                "Межсегментные расчёты (Городские сервисы)"]
    for s, year, v in tick_chart(92, 293.1, subs_rev, 130, 290):
        emit(tid, "Выручка", s, year, v, "млрд_руб", 92)
    subs_eb = ["Райдтех", "Райдтех", "Сервисы электронной коммерции",
               "Сервисы электронной коммерции", "Доставка и другие O2O-сервисы",
               "Доставка и другие O2O-сервисы"]
    got = tick_chart(92, 621.8, subs_eb[2:4], 500, 700) + \
        tick_chart(92, 647.0, subs_eb[0:2] + subs_eb[4:6], 500, 700)
    for s, year, v in got:
        emit(tid, "Скорректированный показатель EBITDA", s, year, v, "млрд_руб", 92)
    subs_gtv = ["Райдтех", "Райдтех", "Сервисы электронной коммерции",
                "Сервисы электронной коммерции", "Доставка и другие O2O-сервисы",
                "Доставка и другие O2O-сервисы"]
    for s, year, v in tick_chart(93, 384.2, subs_gtv, 190, 380):
        emit(tid, "Валовый оборот сервисов (GTV)", s, year, v, "млрд_руб", 93)


def t_personal_breakdown():
    """стр. 94-95: выручка и скорр. EBITDA Персональных сервисов по подсегментам."""
    tid = "personal_services_breakdown"
    SOURCES[tid] = ("vec", [94, 95])
    subs = ["Плюс и развлекательные сервисы", "Плюс и развлекательные сервисы",
            "Финансовые сервисы", "Финансовые сервисы",
            "Свои Плюсы и другие сервисы", "Свои Плюсы и другие сервисы",
            "Межсегментные расчёты (Персональные сервисы)",
            "Межсегментные расчёты (Персональные сервисы)"]
    for s, year, v in tick_chart(94, 348.6, subs, 170, 345):
        emit(tid, "Выручка", s, year, v, "млрд_руб", 94)
    for s, year, v in tick_chart(95, 315.3, subs[:6], 140, 312):
        emit(tid, "Скорректированный показатель EBITDA", s, year, v, "млрд_руб", 95)


def t_share_capital():
    tid, pg = "share_capital", 127
    SOURCES[tid] = ("vec", [pg])
    txt = doc.load_page(pg - 1).get_text("text")

    def grab(pat, u, m):
        g = re.search(pat, txt)
        if g:
            emit(tid, m, None, "2026-02-03", norm_num(g.group(1)), u, pg)
    grab(r"Уставный капитал[^\d]*([\d" + SPACES + r"]+) рублей", "руб", "Уставный капитал")
    grab(r"Общее количество акций:\s*\n?\s*([\d" + SPACES + r"]+) шт", "шт", "Общее количество акций")
    grab(r"([\d" + SPACES + r"]+) шт\. — голосующие", "шт", "Голосующие обыкновенные акции")
    grab(r"([\d" + SPACES + r"]+) шт\. — обыкновенные акции, принадлежащие",
         "шт", "Акции администраторов программы мотивации")
    vals = stream_values(pg, 560, 660, 3)
    for s, v in zip(["Основные акционеры", "Администраторы Программы мотивации",
                     "Акции в свободном обращении"], vals):
        emit(tid, "Структура акционерного капитала", s, "2026-02-03", v, "%", pg)


# ============================================================================
# C. IMG-ГРАФИКИ (растр; значения сняты визуально с рендера страницы)
# ============================================================================
IMG_CHARTS = [
    # (table_id, pg, metric, segment, period, value, unit)
    ("segment_revenue_2025", 87, "Выручка", "Городские сервисы", "2025", 804.5, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка", "Поисковые сервисы и ИИ", "2025", 551.2, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка", "Персональные сервисы", "2025", 214.3, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка", "Б2Б Тех", "2025", 48.2, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка", "Прочие сервисы и инициативы", "2025", 12.1, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка", "Автономные технологии", "2025", 0.6, "млрд_руб"),
    ("segment_revenue_2025", 87, "Выручка (изменение г/г)", "Городские сервисы", "2025", 36, "%"),
    ("segment_revenue_2025", 87, "Выручка (изменение г/г)", "Поисковые сервисы и ИИ", "2025", 10, "%"),
    ("segment_revenue_2025", 87, "Выручка (изменение г/г)", "Персональные сервисы", "2025", 61, "%"),
    ("segment_revenue_2025", 87, "Выручка (изменение г/г)", "Б2Б Тех", "2025", 48, "%"),
    ("segment_revenue_2025", 87, "Выручка (изменение г/г)", "Прочие сервисы и инициативы", "2025", 5, "%"),
    ("segment_revenue_2025", 87, "Доля в выручке по блокам отчётности", "Городские сервисы", "2025", 49, "%"),
    ("segment_revenue_2025", 87, "Доля в выручке по блокам отчётности", "Поисковые сервисы и ИИ", "2025", 34, "%"),
    ("segment_revenue_2025", 87, "Доля в выручке по блокам отчётности", "Персональные сервисы", "2025", 13, "%"),
    ("segment_revenue_2025", 87, "Доля в выручке по блокам отчётности", "Б2Б Тех", "2025", 3, "%"),
    ("segment_revenue_2025", 87, "Доля в выручке по блокам отчётности", "Прочие сервисы и инициативы", "2025", 1, "%"),
    ("segment_revenue_2025", 87, "Коррекция на межсегментные расчёты", None, "2025", -189.7, "млрд_руб"),

    ("capex", 87, "CAPEX", None, "2024", 124.6, "млрд_руб"),
    ("capex", 87, "CAPEX", None, "2025", 145.9, "млрд_руб"),
    ("capex", 87, "CAPEX, % от выручки", None, "2024", 11.4, "%"),
    ("capex", 87, "CAPEX, % от выручки", None, "2025", 10.1, "%"),
    ("capex", 87, "Скорректированный показатель EBITDA", None, "2024", 188.6, "млрд_руб"),
    ("capex", 87, "Скорректированный показатель EBITDA", None, "2025", 280.8, "млрд_руб"),
    ("capex", 87, "Рентабельность по скорректированной EBITDA", None, "2024", 17.2, "%"),
    ("capex", 87, "Рентабельность по скорректированной EBITDA", None, "2025", 19.5, "%"),

    ("operating_leverage_4y", 89, "Скорректированный показатель EBITDA", None, "2022", 72.4, "млрд_руб"),
    ("operating_leverage_4y", 89, "Скорректированный показатель EBITDA", None, "2023", 120.8, "млрд_руб"),
    ("operating_leverage_4y", 89, "Скорректированный показатель EBITDA", None, "2024", 188.6, "млрд_руб"),
    ("operating_leverage_4y", 89, "Скорректированный показатель EBITDA", None, "2025", 280.8, "млрд_руб"),
    ("operating_leverage_4y", 89, "Рентабельность по скорректированной EBITDA", None, "2022", 13.9, "%"),
    ("operating_leverage_4y", 89, "Рентабельность по скорректированной EBITDA", None, "2023", 15.1, "%"),
    ("operating_leverage_4y", 89, "Рентабельность по скорректированной EBITDA", None, "2024", 17.2, "%"),
    ("operating_leverage_4y", 89, "Рентабельность по скорректированной EBITDA", None, "2025", 19.5, "%"),

    ("segment_search_ai", 90, "Выручка", "Поисковые сервисы и ИИ", "2024", 499.8, "млрд_руб"),
    ("segment_search_ai", 90, "Выручка", "Поисковые сервисы и ИИ", "2025", 551.2, "млрд_руб"),
    ("segment_search_ai", 90, "Скорректированный показатель EBITDA", "Поисковые сервисы и ИИ", "2024", 220.1, "млрд_руб"),
    ("segment_search_ai", 90, "Скорректированный показатель EBITDA", "Поисковые сервисы и ИИ", "2025", 245.5, "млрд_руб"),
    ("segment_search_ai", 90, "Рентабельность по скорректированной EBITDA", "Поисковые сервисы и ИИ", "2024", 44.0, "%"),
    ("segment_search_ai", 90, "Рентабельность по скорректированной EBITDA", "Поисковые сервисы и ИИ", "2025", 44.5, "%"),

    ("segment_city", 91, "Выручка", "Городские сервисы", "2024", 592.6, "млрд_руб"),
    ("segment_city", 91, "Выручка", "Городские сервисы", "2025", 804.5, "млрд_руб"),
    ("segment_city", 91, "Скорректированный показатель EBITDA", "Городские сервисы", "2024", 17.6, "млрд_руб"),
    ("segment_city", 91, "Скорректированный показатель EBITDA", "Городские сервисы", "2025", 62.8, "млрд_руб"),
    ("segment_city", 91, "Рентабельность по скорректированной EBITDA", "Городские сервисы", "2024", 3.0, "%"),
    ("segment_city", 91, "Рентабельность по скорректированной EBITDA", "Городские сервисы", "2025", 7.8, "%"),

    ("segment_personal", 94, "Выручка", "Персональные сервисы", "2024", 133.2, "млрд_руб"),
    ("segment_personal", 94, "Выручка", "Персональные сервисы", "2025", 214.3, "млрд_руб"),
    ("segment_personal", 94, "Скорректированный показатель EBITDA", "Персональные сервисы", "2024", -8.7, "млрд_руб"),
    ("segment_personal", 94, "Скорректированный показатель EBITDA", "Персональные сервисы", "2025", 7.0, "млрд_руб"),
    ("segment_personal", 94, "Рентабельность по скорректированной EBITDA", "Персональные сервисы", "2024", -6.5, "%"),
    ("segment_personal", 94, "Рентабельность по скорректированной EBITDA", "Персональные сервисы", "2025", 3.3, "%"),

    ("segment_b2b_tech", 96, "Выручка", "Б2Б Тех", "2024", 32.5, "млрд_руб"),
    ("segment_b2b_tech", 96, "Выручка", "Б2Б Тех", "2025", 48.2, "млрд_руб"),
    ("segment_b2b_tech", 96, "Скорректированный показатель EBITDA", "Б2Б Тех", "2024", 3.9, "млрд_руб"),
    ("segment_b2b_tech", 96, "Скорректированный показатель EBITDA", "Б2Б Тех", "2025", 9.4, "млрд_руб"),
    ("segment_b2b_tech", 96, "Рентабельность по скорректированной EBITDA", "Б2Б Тех", "2024", 12.0, "%"),
    ("segment_b2b_tech", 96, "Рентабельность по скорректированной EBITDA", "Б2Б Тех", "2025", 19.6, "%"),

    ("segment_autonomous", 97, "Выручка", "Автономные технологии", "2024", 0.13, "млрд_руб"),
    ("segment_autonomous", 97, "Выручка", "Автономные технологии", "2025", 0.58, "млрд_руб"),
    ("segment_autonomous", 97, "Скорректированный показатель EBITDA", "Автономные технологии", "2024", -8.3, "млрд_руб"),
    ("segment_autonomous", 97, "Скорректированный показатель EBITDA", "Автономные технологии", "2025", -15.4, "млрд_руб"),
]


def t_img_charts():
    for tid, pg, m, s, p, v, u in IMG_CHARTS:
        if tid not in SOURCES:
            SOURCES[tid] = ("img", [])
        if pg not in SOURCES[tid][1]:
            SOURCES[tid][1].append(pg)
        emit(tid, m, s, p, v, u, pg)


# ============================================================================
def main():
    steps = [t_main_financials, t_corp_code, t_committees, t_board_pay, t_share_issues,
             t_share_trading, t_analysts, t_dividends,
             t_key_metrics_3y, t_revenue_distribution_21, t_search_market,
             t_plus_quarterly, t_city_breakdown, t_personal_breakdown, t_share_capital,
             t_img_charts]
    for fn in steps:
        n0 = len(RECORDS)
        try:
            fn()
        except Exception as e:
            print(f"!! {fn.__name__}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        print(f"{fn.__name__:28s} +{len(RECORDS)-n0} записей")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in RECORDS:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"\nвсего записей: {len(RECORDS)}")
    print(f"таблиц: {len(SOURCES)}")
    pages = sorted({r['pg'] for r in RECORDS})
    print(f"страниц покрыто: {len(pages)} -> {pages}")
    with open(r"D:\Python\annual-report-qa\build\sources.json", "w", encoding="utf-8") as f:
        json.dump(SOURCES, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

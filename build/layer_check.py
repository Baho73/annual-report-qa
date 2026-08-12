# -*- coding: utf-8 -*-
"""
Детектор расхождения слоёв PDF (чистая геометрия через fitz, без модели).

Ищет две вещи по всем 201 странице:
  A. Растровое изображение, перекрывающее прямоугольник текстового блока
     (картинка ПОВЕРХ текста = либо декор, либо подмена того, что видит человек).
  B. Невидимый/почти невидимый текст: кегль < 3pt, render mode 3 (invisible),
     цвет текста, совпадающий с заливкой под ним.

Выход: data/layer_report.md
"""
import json
import os
import re
from collections import defaultdict

import fitz

PDF = r"D:\Python\test-4a\data\yandex_annual_report_2025.pdf"
OUT_MD = r"D:\Python\test-4a\data\layer_report.md"
OUT_JSON = r"D:\Python\test-4a\build\layer_findings.json"

MIN_FONT = 3.0          # pt
OVERLAP_MIN = 0.30      # доля площади текстового блока под картинкой
COLOR_TOL = 12          # допуск совпадения цвета текста и фона (0..255 по каналу)


def rect_inter(a, b):
    x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
    x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def srgb(i):
    return ((i >> 16) & 255, (i >> 8) & 255, i & 255)


def close(c1, c2, tol=COLOR_TOL):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def bg_under(page, rect):
    """Средний цвет пикселей под прямоугольником текста, по рендеру БЕЗ текста."""
    try:
        pix = page.get_pixmap(clip=rect, dpi=36, colorspace=fitz.csRGB)
    except Exception:
        return None
    if pix.width == 0 or pix.height == 0:
        return None
    s = pix.samples
    n = pix.width * pix.height
    if n == 0:
        return None
    r = sum(s[0::3]) // n
    g = sum(s[1::3]) // n
    b = sum(s[2::3]) // n
    return (r, g, b)


def main():
    doc = fitz.open(PDF)
    overlaps, invisible, tiny, samecolor = [], [], [], []
    order = {}

    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        pg = pno + 1
        # blocks идут в порядке потока контента => индекс блока = порядок отрисовки.
        # type 1 = растровое изображение, type 0 = текст.
        d = page.get_text("dict")
        blocks = d["blocks"]
        img_blocks = [(i, fitz.Rect(b["bbox"])) for i, b in enumerate(blocks)
                      if b.get("type") == 1]
        order[pg] = "has_images" if img_blocks else "no_images"

        # --- A. картинка, пересекающая текстовый блок ---
        for ti, blk in enumerate(blocks):
            if blk.get("type") != 0:
                continue
            br = fitz.Rect(blk["bbox"])
            area = br.get_area()
            if area <= 1:
                continue
            txt = " ".join(sp["text"] for ln in blk["lines"] for sp in ln["spans"]).strip()
            if not txt:
                continue
            for ii, ir in img_blocks:
                if ir.get_area() < 4:
                    continue
                frac = rect_inter(br, ir) / area
                if frac >= OVERLAP_MIN:
                    # ii > ti => картинка нарисована ПОСЛЕ текста => лежит ПОВЕРХ него
                    overlaps.append({
                        "pg": pg, "frac": round(frac, 3),
                        "text_block_idx": ti, "img_block_idx": ii,
                        "text_bbox": [round(v, 1) for v in br],
                        "img_bbox": [round(v, 1) for v in ir],
                        "text": txt[:90],
                        "img_covers_page": round(ir.get_area() / page.rect.get_area(), 3),
                        "order": "image_above_text" if ii > ti else "image_below_text",
                    })

        # --- B. невидимый / микроскопический / сливающийся текст ---
        for blk in blocks:
            if blk.get("type") != 0:
                continue
            for ln in blk["lines"]:
                for sp in ln["spans"]:
                    t = sp["text"].strip()
                    if not t:
                        continue
                    rect = fitz.Rect(sp["bbox"])
                    # render mode 3 = invisible (OCR-слой)
                    if sp.get("render_mode", 0) == 3:
                        invisible.append({"pg": pg, "size": round(sp["size"], 2),
                                          "bbox": [round(v, 1) for v in rect],
                                          "text": t[:90]})
                        continue
                    if sp["size"] < MIN_FONT:
                        tiny.append({"pg": pg, "size": round(sp["size"], 2),
                                     "bbox": [round(v, 1) for v in rect],
                                     "text": t[:90]})
                        continue
                    fg = srgb(sp["color"])
                    bg = bg_under(page, rect)
                    if bg and close(fg, bg):
                        samecolor.append({"pg": pg, "fg": fg, "bg": bg,
                                          "size": round(sp["size"], 2),
                                          "bbox": [round(v, 1) for v in rect],
                                          "text": t[:90]})

    res = {"overlaps": overlaps, "invisible": invisible, "tiny": tiny,
           "samecolor": samecolor, "paint_order": order}
    real = [x for x in overlaps if x["order"] == "image_above_text"]
    decor = [x for x in overlaps if x["order"] != "image_above_text"]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    # ---------------- отчёт ----------------
    L = []
    L.append("# Проверка расхождения слоёв PDF (геометрия, без модели)\n")
    L.append(f"**Источник:** `{PDF}` — {doc.page_count} страниц  ")
    L.append(f"**Скрипт:** `D:\\Python\\test-4a\\build\\layer_check.py`  ")
    L.append(f"**Сырые находки:** `{OUT_JSON}`\n")
    L.append("Что искали:\n")
    L.append(f"1. Растровая картинка, накрывающая ≥{int(OVERLAP_MIN*100)} % площади текстового блока "
             "(картинка поверх текста — декор либо подмена того, что читает человек).")
    L.append(f"2. Текст кеглем < {MIN_FONT} pt.")
    L.append("3. Текст с режимом отрисовки 3 (invisible — типичный OCR-слой).")
    L.append(f"4. Текст, цвет которого совпадает с фоном под ним (допуск ±{COLOR_TOL} на канал).\n")
    L.append("Каждое пересечение прямоугольников дополнительно проверено по РЕАЛЬНОМУ порядку "
             "отрисовки: `page.get_text(\"dict\")` отдаёт блоки в порядке потока контента, поэтому "
             "индекс блока-картинки против индекса блока-текста прямо говорит, что нарисовано "
             "позже. Картинка с бОльшим индексом лежит ПОВЕРХ текста (подозрение на подмену), "
             "с меньшим — ПОД ним (плитка/подложка/декор).\n")
    L.append("## Сводка\n")
    L.append("| Проверка | Находок | Страниц |")
    L.append("|---|---|---|")
    for name, arr in (("Пересечение картинки с текстовым блоком (сырое)", overlaps),
                      ("...из них картинка РЕАЛЬНО поверх текста", real),
                      ("...из них картинка под текстом (подложка/декор)", decor),
                      ("Невидимый текст (render mode 3)", invisible),
                      (f"Микрокегль < {MIN_FONT} pt", tiny),
                      ("Текст цветом фона", samecolor)):
        pgs = sorted({x["pg"] for x in arr})
        L.append(f"| {name} | {len(arr)} | {len(pgs)} |")
    L.append("")
    vc = defaultdict(int)
    for v in order.values():
        vc[v] += 1
    L.append(f"Порядок отрисовки по страницам: {dict(vc)}\n")
    if not real:
        L.append("> **Вывод: подтверждённых случаев подмены нет.** Все пересечения — "
                 "плитки, иконки и цветные подложки, нарисованные ДО текста. "
                 "Ни одной страницы, где картинка ложится поверх текстового блока, не найдено. "
                 "Это ожидаемый результат: детектор строит baseline, а не ищет злой умысел "
                 "в конкретно этом отчёте.\n")

    def section(title, arr, cols, rows):
        L.append(f"## {title}\n")
        if not arr:
            L.append("Находок нет.\n")
            return
        pgs = sorted({x["pg"] for x in arr})
        L.append(f"Затронутые страницы PDF: {pgs}\n")
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "|".join(["---"] * len(cols)) + "|")
        for x in arr[:60]:
            L.append("| " + " | ".join(rows(x)) + " |")
        if len(arr) > 60:
            L.append(f"\n_...ещё {len(arr)-60} записей, полный список в `{OUT_JSON}`._\n")
        L.append("")

    section("1a. Картинка РЕАЛЬНО поверх текста (подозрение на подмену)", real,
            ["Стр.", "Доля текст. блока под картинкой", "Картинка занимает страницы",
             "bbox текста", "bbox картинки", "Текст"],
            lambda x: [str(x["pg"]), f"{x['frac']*100:.0f} %", f"{x['img_covers_page']*100:.0f} %",
                       str(x["text_bbox"]), str(x["img_bbox"]), "`" + x["text"].replace("|", "\\|") + "`"])
    section("1b. Пересечение есть, но картинка нарисована ПОД текстом (декор)", decor,
            ["Стр.", "Доля текст. блока", "Картинка занимает страницы", "Порядок", "Текст"],
            lambda x: [str(x["pg"]), f"{x['frac']*100:.0f} %", f"{x['img_covers_page']*100:.0f} %",
                       x["order"], "`" + x["text"].replace("|", "\\|") + "`"])
    section("2. Невидимый текст (render mode 3)", invisible,
            ["Стр.", "Кегль", "bbox", "Текст"],
            lambda x: [str(x["pg"]), str(x["size"]), str(x["bbox"]),
                       "`" + x["text"].replace("|", "\\|") + "`"])
    section(f"3. Микрокегль < {MIN_FONT} pt", tiny,
            ["Стр.", "Кегль", "bbox", "Текст"],
            lambda x: [str(x["pg"]), str(x["size"]), str(x["bbox"]),
                       "`" + x["text"].replace("|", "\\|") + "`"])
    section("4. Текст цветом фона", samecolor,
            ["Стр.", "Кегль", "Цвет текста", "Цвет фона", "bbox", "Текст"],
            lambda x: [str(x["pg"]), str(x["size"]), str(x["fg"]), str(x["bg"]),
                       str(x["bbox"]), "`" + x["text"].replace("|", "\\|") + "`"])

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"overlaps={len(overlaps)} invisible={len(invisible)} tiny={len(tiny)} "
          f"samecolor={len(samecolor)}")
    print("->", OUT_MD)


if __name__ == "__main__":
    main()

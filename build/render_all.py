# -*- coding: utf-8 -*-
"""Рендер всех страниц годового отчёта в PNG 200 dpi -> build/pages/pNNN.png"""
import os
import sys

import fitz

PDF = r"D:\Python\test-4a\data\yandex_annual_report_2025.pdf"
OUT = r"D:\Python\test-4a\build\pages"


def main():
    os.makedirs(OUT, exist_ok=True)
    doc = fitz.open(PDF)
    n = doc.page_count
    made = 0
    for i in range(n):
        path = os.path.join(OUT, f"p{i+1:03d}.png")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        pix = doc.load_page(i).get_pixmap(dpi=200)
        pix.save(path)
        made += 1
    sizes = [os.path.getsize(os.path.join(OUT, f"p{i+1:03d}.png")) for i in range(n)]
    print(f"pages={n} rendered_now={made} total_mb={sum(sizes)/1e6:.1f} "
          f"min_kb={min(sizes)/1e3:.0f} max_kb={max(sizes)/1e3:.0f}")


if __name__ == "__main__":
    main()

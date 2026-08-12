"""Дамп текста произвольных страниц PDF. Usage: python dump_pages.py 21 86 90-96"""
import sys, re
import fitz

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"


def parse_args(args):
    pages = []
    for a in args:
        if "-" in a:
            s, e = a.split("-")
            pages.extend(range(int(s), int(e) + 1))
        else:
            pages.append(int(a))
    return pages


doc = fitz.open(PDF)
for pno in parse_args(sys.argv[1:]):
    p = doc.load_page(pno - 1)
    txt = p.get_text("text")
    print(f"\n{'='*80}\n=== PAGE {pno} ===\n{'='*80}")
    print(txt)

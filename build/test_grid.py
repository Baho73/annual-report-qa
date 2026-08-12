"""Проба сеточных таблиц pdfplumber. Usage: python test_grid.py 86 105"""
import sys, json
import pdfplumber

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"
pages = [int(x) for x in sys.argv[1:]]

with pdfplumber.open(PDF) as pdf:
    for pno in pages:
        page = pdf.pages[pno - 1]
        tabs = page.find_tables()
        print(f"\n=== PAGE {pno}: {len(tabs)} tables ===")
        for i, t in enumerate(tabs):
            data = t.extract()
            print(f"--- table {i} bbox={tuple(round(v,1) for v in t.bbox)} rows={len(data)} ---")
            for row in data:
                cells = ["" if c is None else " ".join(c.split()) for c in row]
                print("  |", " | ".join(cells))

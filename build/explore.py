"""Разведка PDF: где таблицы, какие страницы, что за текст."""
import sys, io, re, json
import fitz

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"

doc = fitz.open(PDF)
print("pages:", doc.page_count)

# 1. Ищем страницы с явными числовыми паттернами (число с пробелом-разделителем и запятой)
num_re = re.compile(r"\d[\d\u00a0\u202f ]*[,]\d")
big_re = re.compile(r"\d{1,3}[\u00a0\u202f ]\d{3}")

rows = []
for i in range(doc.page_count):
    p = doc.load_page(i)
    txt = p.get_text("text")
    tabs = p.find_tables()
    n_tab = len(tabs.tables)
    n_num = len(num_re.findall(txt)) + len(big_re.findall(txt))
    first = txt.strip().split("\n")[0][:70] if txt.strip() else ""
    rows.append((i + 1, n_tab, n_num, len(txt), first))

for r in rows:
    if r[1] > 0 or r[2] >= 4:
        print(f"p{r[0]:>3} tables={r[1]} nums={r[2]:>3} len={r[3]:>5} | {r[4]}")

"""Дамп слов с координатами. Usage: python dump_words.py 92 [ymin ymax]"""
import sys
import fitz

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"
doc = fitz.open(PDF)
pno = int(sys.argv[1])
ymin = float(sys.argv[2]) if len(sys.argv) > 2 else -1e9
ymax = float(sys.argv[3]) if len(sys.argv) > 3 else 1e9

p = doc.load_page(pno - 1)
print("page rect:", p.rect)
words = p.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
words.sort(key=lambda w: (round(w[1], 1), w[0]))
for w in words:
    if ymin <= w[1] <= ymax:
        print(f"x0={w[0]:7.1f} y0={w[1]:7.1f} x1={w[2]:7.1f} y1={w[3]:7.1f}  {w[4]!r}")

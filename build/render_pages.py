"""Рендер страниц в PNG для визуальной проверки. Usage: python render_pages.py 87 89 90"""
import sys, os
import fitz

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"
OUT = r"D:\Python\annual-report-qa\build\png"
os.makedirs(OUT, exist_ok=True)

doc = fitz.open(PDF)
for a in sys.argv[1:]:
    pno = int(a)
    p = doc.load_page(pno - 1)
    pix = p.get_pixmap(dpi=170)
    path = os.path.join(OUT, f"p{pno:03d}.png")
    pix.save(path)
    print(path, pix.width, "x", pix.height)

"""Проверка: есть ли на странице растровые изображения (графики-картинки) и сколько."""
import sys
import fitz

PDF = r"D:\Python\annual-report-qa\data\yandex_annual_report_2025.pdf"
doc = fitz.open(PDF)

pages = [int(x) for x in sys.argv[1:]] or list(range(1, doc.page_count + 1))
for pno in pages:
    p = doc.load_page(pno - 1)
    imgs = p.get_images(full=True)
    drawings = p.get_drawings()
    txt = p.get_text("text")
    import re
    nums = re.findall(r"[-+(]?\d[\d\u00a0\u202f ]*(?:[,.]\d+)?\)?%?", txt)
    print(f"p{pno:>3} images={len(imgs)} drawings={len(drawings)} numtokens={len(nums)}")
    for im in imgs:
        print(f"      xref={im[0]} {im[2]}x{im[3]} name={im[7]}")

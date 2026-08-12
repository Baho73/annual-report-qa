# -*- coding: utf-8 -*-
"""Читаемый дамп tables.json (по таблицам)."""
import json, sys, collections

P = r"D:\Python\annual-report-qa\data\tables.json"
recs = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
only = sys.argv[1:] or None
by = collections.OrderedDict()
for r in recs:
    by.setdefault(r["t"], []).append(r)
for t, rs in by.items():
    if only and t not in only:
        continue
    pgs = sorted({r["pg"] for r in rs})
    print(f"\n### {t}  ({len(rs)} записей, стр. {pgs})")
    for r in rs:
        print(f"  pg{r['pg']:>3} | {r['m'][:58]:58s} | {str(r['s'])[:38]:38s} | "
              f"{r['p']:>10} | {r['v']:>16} | {r['u']}")
print(f"\nИТОГО: {len(recs)} записей, {len(by)} таблиц")

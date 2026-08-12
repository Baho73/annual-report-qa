# -*- coding: utf-8 -*-
"""Проверки извлечённых таблиц (checks 1, 2, 4 + кросс-сверка источников)."""
import json
import collections

P = r"D:\Python\annual-report-qa\data\tables.json"
R = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]


def find(**kw):
    out = []
    for r in R:
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r)
    return out


print("=" * 78)
print("ПРОВЕРКА 1. Контрольные цифры")
print("=" * 78)
controls = [
    ("консолидированная выручка 2025", 1441.1,
     [("main_financials", "Выручка", None, "2025"),
      ("revenue_distribution_2025", "Выручка (консолидированная)", None, "2025"),
      ("key_financials_3y", "Выручка", None, "2025")]),
    ("Поисковые сервисы и ИИ, выручка 2025", 551.2,
     [("revenue_distribution_2025", "Выручка", "Поисковые сервисы и ИИ", "2025"),
      ("segment_revenue_2025", "Выручка", "Поисковые сервисы и ИИ", "2025"),
      ("segment_search_ai", "Выручка", "Поисковые сервисы и ИИ", "2025")]),
    ("Городские сервисы, выручка 2025", 804.5,
     [("revenue_distribution_2025", "Выручка", "Городские сервисы", "2025"),
      ("segment_revenue_2025", "Выручка", "Городские сервисы", "2025"),
      ("segment_city", "Выручка", "Городские сервисы", "2025")]),
    ("Персональные сервисы, выручка 2025", 214.3,
     [("revenue_distribution_2025", "Выручка", "Персональные сервисы", "2025"),
      ("segment_revenue_2025", "Выручка", "Персональные сервисы", "2025"),
      ("segment_personal", "Выручка", "Персональные сервисы", "2025")]),
    ("Б2Б Тех, выручка 2025", 48.2,
     [("revenue_distribution_2025", "Выручка", "Б2Б Тех", "2025"),
      ("segment_revenue_2025", "Выручка", "Б2Б Тех", "2025"),
      ("segment_b2b_tech", "Выручка", "Б2Б Тех", "2025")]),
]
ok_all = True
for name, expect, keys in controls:
    hits = []
    for t, m, s, p in keys:
        for r in find(t=t, m=m, s=s, p=p):
            hits.append((r["t"], r["pg"], r["v"]))
    good = hits and all(abs(v - expect) < 1e-9 for _, _, v in hits)
    ok_all &= bool(good)
    print(f"  [{'OK ' if good else 'FAIL'}] {name}: ожидалось {expect}; "
          f"найдено {len(hits)} раз(а) -> " +
          ", ".join(f"{t}@стр.{pg}={v}" for t, pg, v in hits))
print(f"\n  ИТОГ проверки 1: {'все контрольные цифры найдены и совпали' if ok_all else 'ЕСТЬ РАСХОЖДЕНИЯ'}")

print()
print("=" * 78)
print("ПРОВЕРКА 2. Сумма сегментов vs консолидированная выручка")
print("=" * 78)
for src in ("revenue_distribution_2025", "segment_revenue_2025"):
    segs = [r for r in find(t=src, m="Выручка", p="2025")]
    tot = sum(r["v"] for r in segs)
    print(f"\n  Источник: {src} (стр. {sorted({r['pg'] for r in segs})})")
    for r in sorted(segs, key=lambda r: -r["v"]):
        print(f"    {r['s']:32s} {r['v']:>8}")
    print(f"    {'СУММА СЕГМЕНТОВ':32s} {round(tot,1):>8}")
    cons = 1441.1
    d = tot - cons
    print(f"    {'Консолидированная выручка':32s} {cons:>8}")
    print(f"    {'Расхождение':32s} {round(d,1):>8}  ({d/cons*100:.2f}%)")
    elim = find(t=src, m="Коррекция на межсегментные расчёты")
    if elim:
        e = elim[0]["v"]
        d2 = tot + e - cons
        print(f"    Коррекция на межсегментные расчёты: {e}")
        print(f"    Сумма сегментов + коррекция = {round(tot+e,1)}; "
              f"остаточное расхождение {round(d2,2)} ({d2/cons*100:.3f}%) — округление")

print()
print("=" * 78)
print("ПРОВЕРКА 4. Абсурдные значения и кросс-сверка источников")
print("=" * 78)
flags = []
for r in R:
    v, u = r["v"], r["u"]
    if u == "млрд_руб" and abs(v) > 2000:
        flags.append(("млрд_руб > 2000 (подозрение на млн/млрд)", r))
    if u == "млн_руб" and abs(v) > 100000:
        flags.append(("млн_руб > 100 000", r))
    if u == "%" and not (-100 <= v <= 1000):
        flags.append(("% вне [-100;1000]", r))
    if u == "млн" and abs(v) > 1000:
        flags.append(("млн (пользователи) > 1000", r))
if flags:
    for why, r in flags:
        print(f"  [FLAG] {why}: {r}")
else:
    print("  [OK ] абсурдных значений по правилам диапазонов не найдено")

# кросс-сверка: один и тот же (метрика, сегмент, период) в разных таблицах
key = collections.defaultdict(list)
for r in R:
    key[(r["m"], r["s"], r["p"], r["u"])].append(r)
mism = 0
dupl = 0
for k, rs in sorted(key.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
    vals = {r["v"] for r in rs}
    if len(rs) > 1:
        dupl += 1
        if len(vals) > 1:
            mism += 1
            print(f"  [MISMATCH] {k}: " + ", ".join(f"{r['t']}@стр.{r['pg']}={r['v']}" for r in rs))
print(f"\n  Пересекающихся ключей (метрика+сегмент+период+единица) в разных таблицах: {dupl}")
print(f"  Из них расхождений: {mism}")

# внутренняя арифметика: рентабельность = EBITDA / выручка
print()
print("  Сверка производных: рентабельность по скорр. EBITDA = EBITDA / выручка")
pairs = [("Группа", "main_financials", None, "capex"),
         ("Поисковые сервисы и ИИ", "segment_search_ai", "Поисковые сервисы и ИИ", None),
         ("Городские сервисы", "segment_city", "Городские сервисы", None),
         ("Персональные сервисы", "segment_personal", "Персональные сервисы", None),
         ("Б2Б Тех", "segment_b2b_tech", "Б2Б Тех", None)]
for name, t, s, t2 in pairs:
    for p in ("2024", "2025"):
        rev = find(t=t, m="Выручка", s=s, p=p) or find(t="main_financials", m="Выручка", p=p)
        eb = (find(t=t, m="Скорректированный показатель EBITDA", s=s, p=p) or
              find(t=t2 or t, m="Скорректированный показатель EBITDA", s=s, p=p))
        mg = (find(t=t, m="Рентабельность по скорректированной EBITDA", s=s, p=p) or
              find(t=t2 or t, m="Рентабельность по скорректированной EBITDA", s=s, p=p) or
              find(t=t, m="Рентабельность скорректированного показателя EBITDA", s=s, p=p))
        if rev and eb and mg:
            calc = eb[0]["v"] / rev[0]["v"] * 100
            d = calc - mg[0]["v"]
            mark = "OK " if abs(d) <= 0.35 else "CHK"
            print(f"    [{mark}] {name:26s} {p}: {eb[0]['v']}/{rev[0]['v']} = {calc:6.2f}% "
                  f"vs заявлено {mg[0]['v']}% (Δ {d:+.2f} п.п.)")

# суммы подсегментов
print()
print("  Сверка подсегментов с итогом сегмента")
checks = [("Городские сервисы", "city_services_breakdown", "Выручка", "segment_city", "Выручка"),
          ("Городские сервисы", "city_services_breakdown", "Скорректированный показатель EBITDA",
           "segment_city", "Скорректированный показатель EBITDA"),
          ("Персональные сервисы", "personal_services_breakdown", "Выручка",
           "segment_personal", "Выручка"),
          ("Персональные сервисы", "personal_services_breakdown",
           "Скорректированный показатель EBITDA", "segment_personal",
           "Скорректированный показатель EBITDA")]
for name, t_sub, m_sub, t_tot, m_tot in checks:
    for p in ("2024", "2025"):
        subs = find(t=t_sub, m=m_sub, p=p)
        tot = find(t=t_tot, m=m_tot, s=name, p=p)
        if not subs or not tot:
            continue
        ssum = round(sum(r["v"] for r in subs), 1)
        d = round(ssum - tot[0]["v"], 1)
        mark = "OK " if abs(d) <= 0.3 else "CHK"
        print(f"    [{mark}] {name:22s} {m_sub[:28]:28s} {p}: сумма {ssum} vs итог {tot[0]['v']} (Δ {d})")

print()
print(f"ВСЕГО ЗАПИСЕЙ: {len(R)}; ТАБЛИЦ: {len({r['t'] for r in R})}; "
      f"СТРАНИЦ: {len({r['pg'] for r in R})}")

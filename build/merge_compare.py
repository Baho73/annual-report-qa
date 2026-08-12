# -*- coding: utf-8 -*-
"""
Сборка результата vision-прогона, сверка с парсером, объединённый датасет.

Читает:
  build/vision_cache/pNNN.json   — сырые ответы модели по страницам
  data/tables.json               — результат парсера (266 записей)

Пишет:
  data/tables_vision.json        — JSON Lines, записи vision (+ pg, src="vision")
  data/inventory.json            — JSON Lines, инвентарь визуальных объектов (+ pg)
  data/tables_merged.json        — объединение, у каждой записи src и confirmed
  build/compare.json             — сырой результат сверки для отчёта
"""
import json
import os
import re
from collections import defaultdict

ROOT = r"D:\Python\test-4a"
CACHE = os.path.join(ROOT, "build", "vision_cache")
PARSER = os.path.join(ROOT, "data", "tables.json")
OUT_V = os.path.join(ROOT, "data", "tables_vision.json")
OUT_INV = os.path.join(ROOT, "data", "inventory.json")
OUT_M = os.path.join(ROOT, "data", "tables_merged.json")
OUT_CMP = os.path.join(ROOT, "build", "compare.json")

# ---------------------------------------------------------------- нормализация
SPACES = "\u00a0\u202f\u2009\u2007\u2060"

CANON = [
    (r"скорр\w*\s+показател\w*\s+ebitda|скорр\w*\s+ebitda|"
     r"скорректированн\w+\s+ebitda", "ebitda_adj"),
    (r"рентабельност\w*\s+по\s+скорр\w*\s*(показател\w*)?\s*ebitda|"
     r"рентабельност\w*\s+скорр\w*\s*(показател\w*)?\s*ebitda", "ebitda_margin"),
    (r"скорр\w*\s+чист\w+\s+прибыл\w*", "net_profit_adj"),
    (r"чист\w+\s+прибыл\w*", "net_profit"),
    (r"операционн\w+\s+прибыл\w*", "op_profit"),
    (r"операционн\w+\s+расход\w*", "op_cost"),
    (r"валов\w+\s+оборот|gtv", "gtv"),
    (r"capex\s*,?\s*%\s*от\s+выручки|capex\s+%", "capex_pct"),
    (r"\bcapex\b", "capex"),
    (r"выручк\w*", "revenue"),
    (r"дол\w+\s+в\s+выручке|распределени\w+\s+выручк\w*", "revenue_share"),
    (r"подписчик\w*", "subscribers"),
    (r"\bmau\b", "mau"),
    (r"дол\w+\s+поиск\w*|дол\w+\s+яндекса\s+на\s+российск\w+\s+поисков\w+", "search_share"),
    (r"дивиденд\w*\s+на\s+одну\s+акци\w*|дивиденд\w*\s+на\s+акци\w*", "div_per_share"),
    (r"обща\w+\s+сумм\w+\s+дивиденд\w*", "div_total"),
    (r"коррекци\w+\s+на\s+межсегментн\w+", "intersegment"),
]

CHG = re.compile(r"изменени\w*|прирост|рост\b|г/г|yoy")


def norm_text(s):
    if s is None:
        return ""
    s = str(s).lower()
    for ch in SPACES:
        s = s.replace(ch, " ")
    s = s.replace("ё", "е")
    s = re.sub(r"[«»\"'`().,:;*]", " ", s)
    s = re.sub(r"[-–—]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canon_metric(m):
    """Каноническое имя метрики + флаг 'это изменение/прирост, а не значение'."""
    t = norm_text(m)
    is_chg = bool(CHG.search(t))
    t2 = CHG.sub(" ", t)
    t2 = re.sub(r"\s+", " ", t2).strip()
    for pat, name in CANON:
        if re.search(pat, t2):
            return name, is_chg, t2
    return t2, is_chg, t2


def toks(s):
    return {w for w in norm_text(s).split() if len(w) > 2}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


PER_MAP = {"2024_итоговый": "2024fin", "1п2024": "1h2024", "1п2025": "1h2025"}


def norm_period(p):
    if p is None:
        return ""
    raw = str(p).strip()
    # 28.05.2025 -> 2025-05-28 (парсер пишет датой РФ, модель — ISO)
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    t = norm_text(p)
    t = PER_MAP.get(raw, t)
    t = t.replace("кв'", "кв").replace("к'", "кв")
    m = re.match(r"^(\d)\s*кв\s*(\d{4})$", t)
    if m:
        return f"{m.group(1)}кв{m.group(2)}"
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})$", t)
    if m:
        return t
    return t


UNIT_MAP = {"млрд руб": "млрд_руб", "млрд рублей": "млрд_руб", "млрд_руб": "млрд_руб",
            "млн руб": "млн_руб", "млн рублей": "млн_руб", "млн_руб": "млн_руб",
            "руб": "руб", "рублей": "руб", "%": "%", "п.п.": "п.п.", "пп": "п.п.",
            "шт": "шт", "штук": "шт", "млн": "млн", "млрд": "млрд"}


def norm_unit(u):
    if u is None:
        return ""
    t = str(u).strip().lower().replace("ё", "е")
    return UNIT_MAP.get(t, UNIT_MAP.get(norm_text(t), t))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def same_value(a, b):
    """Совпало ли значение с допуском на округление отчёта (1 знак после запятой)."""
    a, b = num(a), num(b)
    if a is None or b is None:
        return False
    if a == b:
        return True
    d = abs(a - b)
    if d <= 0.051:                      # 0,58 vs 0,6 — округление самого отчёта
        return True
    scale = max(abs(a), abs(b))
    return d / scale <= 0.005 if scale else False


# ---------------------------------------------------------------- загрузка
def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_vision():
    recs, inv, meta = [], [], []
    for pno in range(1, 202):
        p = os.path.join(CACHE, f"p{pno:03d}.json")
        if not os.path.exists(p):
            meta.append({"pg": pno, "status": "missing"})
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        u = d.get("usage", {})
        meta.append({"pg": pno, "status": "ok", "model": d.get("model"),
                     "n_obj": len(d.get("objects", [])),
                     "n_rec": len(d.get("records", [])),
                     "cost": u.get("cost"), "in": u.get("prompt"),
                     "out": u.get("completion"), "finish": d.get("finish")})
        for o in d.get("objects", []):
            if not isinstance(o, dict):
                continue
            inv.append({"pg": pno, "kind": o.get("kind"), "title": o.get("title"),
                        "has_numbers": bool(o.get("has_numbers")),
                        "rows": o.get("rows"), "cols": o.get("cols")})
        for r in d.get("records", []):
            if not isinstance(r, dict) or num(r.get("v")) is None:
                continue
            recs.append({"t": r.get("t"), "m": r.get("m"), "s": r.get("s"),
                         "p": r.get("p"), "v": num(r.get("v")), "u": r.get("u"),
                         "pg": pno, "src": "vision"})
    return recs, inv, meta


# ---------------------------------------------------------------- сверка
SPLIT = re.compile(r"\s+[—–-]\s+")


def split_metric(rec):
    """Парсер иногда кладёт категорию в саму метрику ('Доля выполнения — Не соблюдаются'),
    а модель — в поле сегмента. Приводим к одному виду: хвост после тире считаем
    сегментом, если своего сегмента у записи нет."""
    m, s = rec.get("m"), rec.get("s")
    if s or not m:
        return m, s
    parts = SPLIT.split(str(m))
    if len(parts) == 2 and len(parts[1].split()) <= 4:
        return parts[0].strip(), parts[1].strip()
    return m, s


def keyed(rec):
    m, s = split_metric(rec)
    cm, chg, raw = canon_metric(m)
    return {
        "rec": rec,
        "pg": rec["pg"],
        "per": norm_period(rec.get("p")),
        "seg": norm_text(s),
        "cm": cm, "chg": chg,
        "mt": toks(m),
        "st": toks(s),
        "u": norm_unit(rec.get("u")),
        "v": num(rec.get("v")),
    }


def compatible(a, b):
    """Могут ли две записи описывать одну и ту же ячейку."""
    if a["per"] != b["per"]:
        return 0.0
    if a["chg"] != b["chg"]:
        return 0.0
    # единица: '%' и 'п.п.' не смешиваем с деньгами
    ua, ub = a["u"], b["u"]
    money = {"млрд_руб", "млн_руб", "руб"}
    if ua and ub and ua != ub:
        if (ua in money) != (ub in money):
            return 0.0
    # Метрика. Стороны по-разному раскладывают текст между полями m и s
    # (парсер: m='Голосующие обыкновенные акции', s=None; модель:
    # m='Количество акций', s='Голосующие обыкновенные акции'), поэтому
    # сравниваем и поля по отдельности, и их объединение.
    amс, bmc = a["mt"] | a["st"], b["mt"] | b["st"]
    if a["cm"] == b["cm"]:
        mscore = 1.0
    else:
        mscore = max(jac(a["mt"], b["mt"]), jac(amс, bmc))
        if mscore < 0.34:
            return 0.0
    # Сегмент
    if a["seg"] and b["seg"]:
        sj = jac(a["st"], b["st"])
        if a["seg"] != b["seg"] and sj < 0.5:
            return 0.0
        sscore = 1.0 if a["seg"] == b["seg"] else sj
    elif a["seg"] or b["seg"]:
        # у одной стороны сегмента нет: он мог уехать в метрику. Если метрика
        # пустой стороны покрывает сегмент непустой — это одна и та же ячейка,
        # иначе пара слабая и уступает любому нормальному совпадению сегментов.
        seg_t = a["st"] or b["st"]
        m_t = b["mt"] if a["st"] else a["mt"]
        sscore = 0.95 if seg_t and jac(seg_t, m_t) >= 0.5 else 0.45
    else:
        sscore = 1.0
    return mscore * 0.7 + sscore * 0.3


def main():
    vis, inv, meta = load_vision()
    par = load_jsonl(PARSER)
    for r in par:
        r["src"] = "parser"

    with open(OUT_V, "w", encoding="utf-8") as f:
        for r in vis:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    with open(OUT_INV, "w", encoding="utf-8") as f:
        for o in inv:
            f.write(json.dumps(o, ensure_ascii=False, separators=(",", ":")) + "\n")

    P = [keyed(r) for r in par]
    V = [keyed(r) for r in vis]
    by_pg_v = defaultdict(list)
    for i, v in enumerate(V):
        by_pg_v[v["pg"]].append(i)

    used_v = set()
    pairs = []            # (pi, vi, score)
    # жадное сопоставление: сначала все пары с лучшим score
    cand = []
    for pi, p in enumerate(P):
        for vi in by_pg_v.get(p["pg"], []):
            s = compatible(p, V[vi])
            if s > 0:
                # тай-брейк: при РАВНЫХ метаданных (одна метрика, один период,
                # у одной стороны пустой сегмент) выбираем ту пару, где значения
                # сходятся. Это разрешение неоднозначности сопоставления, а не
                # подгонка: пары с разным score тай-брейк не переставляет.
                cand.append((s, 1 if same_value(p["v"], V[vi]["v"]) else 0, pi, vi))
    cand.sort(key=lambda x: (-x[0], -x[1]))
    used_p = set()
    for s, _tb, pi, vi in cand:
        if pi in used_p or vi in used_v:
            continue
        used_p.add(pi)
        used_v.add(vi)
        pairs.append((pi, vi, s))

    confirmed, mismatch = [], []
    for pi, vi, s in pairs:
        pv, vv = P[pi]["v"], V[vi]["v"]
        row = {"pg": P[pi]["pg"], "score": round(s, 2),
               "parser": P[pi]["rec"], "vision": V[vi]["rec"],
               "v_parser": pv, "v_vision": vv}
        (confirmed if same_value(pv, vv) else mismatch).append(row)

    only_p = [P[i]["rec"] for i in range(len(P)) if i not in used_p]
    only_v = [V[i]["rec"] for i in range(len(V)) if i not in used_v]

    # ---------------- объединённый датасет ----------------
    merged = []
    for pi, vi, s in pairs:
        p, v = P[pi]["rec"], V[vi]["rec"]
        ok = same_value(p["v"], v["v"])
        rec = {"t": p["t"], "m": p["m"], "s": p["s"], "p": p["p"],
               "v": p["v"], "u": p["u"], "pg": p["pg"],
               "src": "both", "confirmed": ok}
        if not ok:
            rec["v_parser"] = p["v"]
            rec["v_vision"] = v["v"]
            rec["conflict"] = True
            rec["vision_m"] = v["m"]
            rec["vision_s"] = v["s"]
            rec["vision_u"] = v["u"]
        merged.append(rec)
    for i in range(len(P)):
        if i not in used_p:
            r = dict(P[i]["rec"])
            r["src"] = "parser"
            r["confirmed"] = False
            merged.append(r)
    for i in range(len(V)):
        if i not in used_v:
            r = dict(V[i]["rec"])
            r["src"] = "vision"
            r["confirmed"] = False
            merged.append(r)
    merged.sort(key=lambda r: (r["pg"], str(r.get("t")), str(r.get("m")),
                               str(r.get("s")), str(r.get("p"))))
    with open(OUT_M, "w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

    # ---------------- инвентарь vs извлечение ----------------
    inv_by_pg = defaultdict(list)
    for o in inv:
        inv_by_pg[o["pg"]].append(o)
    rec_by_pg = defaultdict(list)
    for r in vis:
        rec_by_pg[r["pg"]].append(r)
    par_by_pg = defaultdict(list)
    for r in par:
        par_by_pg[r["pg"]].append(r)

    coverage = []
    for pg in range(1, 202):
        objs = inv_by_pg.get(pg, [])
        numobj = [o for o in objs if o["has_numbers"]]
        ts = {r["t"] for r in rec_by_pg.get(pg, []) if r.get("t")}
        tabs = [o for o in numobj if o["kind"] == "table"
                and isinstance(o.get("rows"), int) and isinstance(o.get("cols"), int)]
        cells = sum(o["rows"] * o["cols"] for o in tabs)
        coverage.append({
            "pg": pg, "objects": len(objs), "num_objects": len(numobj),
            "t_groups": len(ts), "delta": len(numobj) - len(ts),
            "vision_recs": len(rec_by_pg.get(pg, [])),
            "parser_recs": len(par_by_pg.get(pg, [])),
            "table_cells_declared": cells, "n_tables": len(tabs),
        })

    out = {"confirmed": confirmed, "mismatch": mismatch,
           "only_parser": only_p, "only_vision": only_v,
           "coverage": coverage, "meta": meta,
           "n_parser": len(par), "n_vision": len(vis), "n_merged": len(merged),
           "n_inventory": len(inv)}
    with open(OUT_CMP, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    cost = sum(float(m.get("cost") or 0) for m in meta if m["status"] == "ok")
    print(f"парсер={len(par)} vision={len(vis)} объединено={len(merged)} инвентарь={len(inv)}")
    print(f"подтверждено={len(confirmed)} расхождений={len(mismatch)} "
          f"только парсер={len(only_p)} только vision={len(only_v)}")
    print(f"стоимость по usage: ${cost:.4f}")


if __name__ == "__main__":
    main()

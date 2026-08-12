# -*- coding: utf-8 -*-
"""
Прогон страниц годового отчёта через vision-модель (OpenRouter).

Каждая страница -> PNG(200dpi) -> модель -> строгий JSON:
  {"objects":[{kind,title,has_numbers,rows,cols}], "records":[{t,m,s,p,v,u}]}

Результат по каждой странице кэшируется в build/vision_cache/pNNN.json,
чтобы повтор не стоил денег. Итог собирается отдельным скриптом.

Запуск:
  python build/vision_extract.py            # все страницы
  python build/vision_extract.py 87 128 1   # только указанные (пилот)
"""
import base64
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = r"D:\Python\test-4a"
PAGES = os.path.join(ROOT, "build", "pages")
CACHE = os.path.join(ROOT, "build", "vision_cache")
PROFILE = r"D:\Python\hh_answer\user_profile.json"

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = ["anthropic/claude-opus-5-fast", "anthropic/claude-fable-5", "openai/gpt-5.5-pro"]
MODEL = os.environ.get("VISION_MODEL", MODELS[0])
WORKERS = int(os.environ.get("VISION_WORKERS", "9"))
TIMEOUT = 300

SYSTEM = """Ты извлекаешь числовые данные из страниц годового отчёта компании (русский язык).
Отвечай ТОЛЬКО валидным JSON без markdown-обёртки и без пояснений.

Формат ответа:
{"objects":[{"kind":"table|chart|infographic|photo|text_only","title":"<подпись или заголовок объекта>","has_numbers":true|false,"rows":<число строк таблицы или null>,"cols":<число колонок или null>}],
 "records":[{"t":"<id таблицы/графика>","m":"<метрика>","s":"<сегмент/подпись ряда или null>","p":"<период: 2025 / 2024 / 4кв2025 / дата>","v":<число>,"u":"<млрд_руб / млн_руб / руб / % / п.п. / шт / млн / null>"}]}

ПРАВИЛА ДЛЯ objects:
- Перечисли ВСЕ визуальные объекты страницы: таблицы, графики, диаграммы, инфографику, фотографии, блоки сплошного текста.
- kind="table" только для настоящих таблиц с сеткой строк/колонок; для них заполни rows (число строк данных, без шапки) и cols (число колонок данных).
- kind="chart" — столбчатые/линейные/круговые диаграммы. kind="infographic" — блоки с выносками и крупными цифрами. kind="photo" — фотографии и декор. kind="text_only" — сплошной текст без чисел.
- has_numbers=true, если из объекта в принципе можно снять числовое значение.

ПРАВИЛА ДЛЯ records:
- Извлеки ВСЕ числовые данные страницы: из таблиц, графиков, диаграмм, выносок, буллетов с цифрами.
- Скобки вокруг числа означают МИНУС: (1 043,0) -> -1043.0
- Пробел (в том числе неразрывный) — разделитель тысяч: 1 441,1 -> 1441.1 ; 1 799 212 780 748 -> 1799212780748
- Запятая — десятичный разделитель.
- Единицу измерения бери из шапки таблицы, подписи оси или заголовка блока и клади в "u". Если единицы нет — null.
- "t" — короткий латинский идентификатор объекта на странице (например main_financials, segment_revenue_chart, plus_subscribers). Один и тот же объект = один и тот же t.
- "m" — название метрики как в отчёте (Выручка, Скорректированный показатель EBITDA, Рентабельность ...).
- "s" — сегмент/подпись ряда или категория (Городские сервисы, Райдтех, Яндекс). null, если разреза нет.
- "p" — период: 2025, 2024, 2023, 4кв2025, 1п2025 или дата в формате YYYY-MM-DD.

КРИТИЧЕСКИ ВАЖНО — НЕ ВЫДУМЫВАЙ:
- Извлекай только те числа, которые РЕАЛЬНО НАПЕЧАТАНЫ на странице.
- Если на графике нет числовых подписей точек (например график динамики котировок — просто линия), НЕ оценивай значения по высоте линии. Такой объект попадает в objects с has_numbers=false, а в records от него ничего не идёт.
- Прочерки, тире, "н/д", "Н/а", "Неприменимо" — это ОТСУТСТВИЕ значения, записи не создавай.
- Проценты роста с плюсом (+25 %) — это отдельная метрика "изменение", а не значение ряда; если извлекаешь, поставь в "m" название с пометкой (изменение г/г).
- Если на странице чисел нет вообще — верни "records": [].
"""

USER = "Извлеки все визуальные объекты и все числовые данные с этой страницы отчёта. Ответ — только JSON."

_lock = threading.Lock()
_stats = {"cost": 0.0, "in": 0, "out": 0, "ok": 0, "fail": 0, "cached": 0}


def key():
    with open(PROFILE, encoding="utf-8") as f:
        return json.load(f)["openrouter_api_key"]


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def parse_json(txt):
    """Модель иногда оборачивает в ```json ... ``` — снимаем обёртку."""
    t = txt.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def call(pno, api_key, model=MODEL, attempt=1):
    path = os.path.join(PAGES, f"p{pno:03d}.png")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + b64(path)}},
                {"type": "text", "text": USER},
            ]},
        ],
        "max_tokens": 16000,
        "usage": {"include": True},
        "reasoning": {"enabled": False},
    }
    r = requests.post(URL, headers={"Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json"},
                      json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    if "choices" not in data:
        raise RuntimeError(f"нет choices: {json.dumps(data)[:400]}")
    txt = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    obj = parse_json(txt)
    return {
        "pg": pno,
        "model": data.get("model", model),
        "objects": obj.get("objects", []),
        "records": obj.get("records", []),
        "usage": {"prompt": usage.get("prompt_tokens"),
                  "completion": usage.get("completion_tokens"),
                  "cost": usage.get("cost")},
        "finish": data["choices"][0].get("finish_reason"),
        "attempt": attempt,
    }


def worker(pno, api_key):
    out = os.path.join(CACHE, f"p{pno:03d}.json")
    if os.path.exists(out):
        try:
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            if "records" in d:
                with _lock:
                    _stats["cached"] += 1
                return pno, "cached", d
        except Exception:
            pass
    last = None
    for i, model in enumerate([MODEL] + MODELS[1:]):
        for attempt in range(1, 3):
            try:
                d = call(pno, api_key, model, attempt)
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                u = d["usage"]
                with _lock:
                    _stats["ok"] += 1
                    _stats["cost"] += float(u.get("cost") or 0)
                    _stats["in"] += int(u.get("prompt") or 0)
                    _stats["out"] += int(u.get("completion") or 0)
                return pno, "ok", d
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(2 * attempt)
        if i == 0 and "HTTP 4" not in str(last):
            break        # не смена модели, а сетевые/парс-ошибки — не эскалируем
    with _lock:
        _stats["fail"] += 1
    with open(os.path.join(CACHE, f"p{pno:03d}.ERR.txt"), "w", encoding="utf-8") as f:
        f.write(str(last))
    return pno, "fail", last


def main():
    os.makedirs(CACHE, exist_ok=True)
    args = [int(a) for a in sys.argv[1:] if a.isdigit()]
    pages = args if args else list(range(1, 202))
    api_key = key()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(worker, p, api_key): p for p in pages}
        done = 0
        for fut in as_completed(futs):
            pno, status, d = fut.result()
            done += 1
            if status == "fail":
                print(f"[{done}/{len(pages)}] p{pno:03d} FAIL {d}", flush=True)
            elif status == "ok":
                print(f"[{done}/{len(pages)}] p{pno:03d} obj={len(d['objects'])} "
                      f"rec={len(d['records'])} in={d['usage']['prompt']} "
                      f"out={d['usage']['completion']} ${d['usage']['cost']}", flush=True)
            if done % 25 == 0:
                with _lock:
                    print(f"  ... промежуточно: ${_stats['cost']:.3f}", flush=True)
    print("\n== ИТОГ ==")
    print(f"модель:  {MODEL}")
    print(f"ok={_stats['ok']} cached={_stats['cached']} fail={_stats['fail']}")
    print(f"tokens: in={_stats['in']} out={_stats['out']}")
    print(f"СТОИМОСТЬ этого прогона: ${_stats['cost']:.4f}")
    if _stats["ok"]:
        print(f"на страницу: ${_stats['cost']/_stats['ok']:.4f} -> "
              f"прогноз на 201: ${_stats['cost']/_stats['ok']*201:.2f}")
    print(f"время: {time.time()-t0:.0f} c")


if __name__ == "__main__":
    main()

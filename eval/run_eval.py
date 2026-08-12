"""M-EVAL: прогон вопросов через режимы поиска и сборка матрицы."""

# FILE: eval/run_eval.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: заменить мнение о выборе архитектуры измерением: один набор вопросов через все режимы.
#   SCOPE: загрузка эталонов, прогон режимов, оценка ответа по числам, страницам и терминам, сборка отчёта.
#   DEPENDS: M-ANSWER, M-ROUTER
#   LINKS: M-EVAL, V-M-EVAL
#   INPUTS: eval/questions.yaml
#   OUTPUTS: eval/results.json, eval/results.md
#   ROLE: SCRIPT
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   load_questions - чтение вопросов с эталонами
#   score - оценка одного ответа против эталона
#   run_one - прогон одного вопроса в одном режиме
#   run - прогон набора через выбранные режимы, с отбором по id
#   render_markdown - таблица результатов для README
#   QUESTIONS_PATH - путь к набору вопросов с эталонами
#   RESULTS_JSON - сырые результаты прогона
#   RESULTS_MD - отчёт прогона в markdown
#   rescore - пересчёт оценок по сохранённым ответам, без обращения к модели
#   main - точка входа с аргументами командной строки
# END_MODULE_MAP

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from report_qa import config  # noqa: E402
from report_qa.answer import ask, numbers_in  # noqa: E402
from report_qa.router import route  # noqa: E402
from report_qa.vector import section_ids_for  # noqa: E402

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.yaml"
RESULTS_JSON = Path(__file__).resolve().parent / "results.json"
RESULTS_MD = Path(__file__).resolve().parent / "results.md"


# START_BLOCK_SCORING
def load_questions():
    with io.open(QUESTIONS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def score(question: dict, answer) -> dict:
    """Оценка ответа против эталона.

    Числа сверяются с допуском на округление, страницы — по пересечению
    с допустимым набором, термины — по вхождению.
    """
    text = answer.text
    text_values = {float(v) for v in numbers_in(text)}

    expected = question.get("expect_values") or []
    hits = []
    for want in expected:
        tolerance = max(abs(want) * 0.005, 0.05)
        hits.append(any(abs(got - want) <= tolerance for got in text_values))
    values_ok = all(hits) if expected else None

    allowed_pages = set(question.get("expect_pages") or [])
    pages_ok = bool(set(answer.cited_pages) & allowed_pages) if allowed_pages else None

    terms = question.get("expect_terms") or []
    terms_ok = all(t.lower() in text.lower() for t in terms) if terms else None

    forbidden = question.get("forbid_terms") or []
    forbidden_hit = [t for t in forbidden if t.lower() in text.lower()]

    # Для вопроса про отсутствующие данные любое число в ответе подозрительно.
    if question.get("forbid_values_any"):
        values_ok = not text_values

    return {
        "values_ok": values_ok,
        "values_expected": expected,
        "pages_ok": pages_ok,
        "cited_pages": answer.cited_pages,
        "terms_ok": terms_ok,
        "forbidden_hit": forbidden_hit,
        "unverified_numbers": answer.unverified_numbers,
        "has_citations": answer.has_citations,
    }


def _passed(card: dict) -> bool:
    checks = [card["values_ok"], card["pages_ok"], card["terms_ok"]]
    return all(c is not False for c in checks) and not card["forbidden_hit"]
# END_BLOCK_SCORING


# START_BLOCK_RUN
def run_one(question: dict, mode: str, model=None) -> dict:
    """Один вопрос в одном режиме. Ошибка не записывается как ноль."""
    section_ids, router_tokens, router_latency = None, 0, 0.0
    effective_mode = mode

    if mode == "router":
        decision = route(question["question"])
        section_ids = decision.section_ids
        router_tokens, router_latency = decision.tokens, decision.latency_s
        effective_mode = decision.mode
    elif mode == "vector":
        # Локальный поиск: модель не вызывается, поэтому в счёт токенов
        # и задержки роутера здесь ничего не добавляется.
        section_ids = section_ids_for(question["question"])

    answer = ask(question["question"], mode=effective_mode,
                 section_ids=section_ids, model=model)
    card = score(question, answer)
    return {
        "id": question["id"],
        "type": question["type"],
        "mode": mode,
        "effective_mode": answer.mode,
        "model": answer.model,
        "passed": _passed(card),
        "prompt_tokens": answer.prompt_tokens + router_tokens,
        "completion_tokens": answer.completion_tokens,
        "latency_s": round(answer.latency_s + router_latency, 2),
        "cost_usd": answer.cost_usd,
        "answer": answer.text,
        **card,
    }


def run(modes=("router",), limit=None, model=None, ids=None) -> list:
    questions = load_questions()
    if ids:
        wanted = {i.strip() for i in ids}
        questions = [q for q in questions if q["id"] in wanted]
    if limit:
        questions = questions[:limit]

    results = []
    for mode in modes:
        for question in questions:
            print(f"  [{mode}] {question['id']} ...", flush=True)
            try:
                row = run_one(question, mode, model=model)
            except Exception as exc:  # noqa: BLE001
                # Провал прогона фиксируется как провал, а не как нулевой результат.
                row = {"id": question["id"], "type": question["type"], "mode": mode,
                       "passed": False, "error": str(exc)[:300],
                       "prompt_tokens": 0, "completion_tokens": 0,
                       "latency_s": 0.0, "cost_usd": 0.0}
            results.append(row)
            flag = "ok " if row.get("passed") else "FAIL"
            print(f"    {flag} стр.{row.get('cited_pages')} "
                  f"{row.get('prompt_tokens')}ток {row.get('latency_s')}с ${row.get('cost_usd')}")
    return results
# END_BLOCK_RUN


# START_BLOCK_REPORT
def render_markdown(results: list) -> str:
    modes = list(dict.fromkeys(r["mode"] for r in results))
    lines = ["# Результаты замера", "", "## Сводка по режимам", "",
             "| Режим | Пройдено | Числа верны | Страницы верны | Медиана токенов | Медиана задержки | Цена набора |",
             "|---|---|---|---|---|---|---|"]

    for mode in modes:
        rows = [r for r in results if r["mode"] == mode]
        total = len(rows)
        passed = sum(1 for r in rows if r.get("passed"))
        values = [r for r in rows if r.get("values_ok") is not None]
        values_ok = sum(1 for r in values if r["values_ok"])
        pages = [r for r in rows if r.get("pages_ok") is not None]
        pages_ok = sum(1 for r in pages if r["pages_ok"])
        toks = sorted(r.get("prompt_tokens", 0) for r in rows)
        lat = sorted(r.get("latency_s", 0) for r in rows)
        cost = sum(r.get("cost_usd", 0) for r in rows)
        median = lambda xs: xs[len(xs) // 2] if xs else 0  # noqa: E731
        lines.append(
            f"| `{mode}` | {passed}/{total} | {values_ok}/{len(values)} | {pages_ok}/{len(pages)} | "
            f"{median(toks):,} | {median(lat)} с | ${cost:.2f} |".replace(",", " ")
        )

    lines += ["", "## По вопросам", "",
              "| Вопрос | Тип | Режим | Итог | Числа | Страницы | Токены | Задержка | Цена |",
              "|---|---|---|---|---|---|---|---|---|"]
    mark = {True: "да", False: "нет", None: "—"}
    for r in results:
        lines.append(
            f'| {r["id"]} | {r["type"]} | `{r["mode"]}` | '
            f'{"пройден" if r.get("passed") else "провал"} | {mark[r.get("values_ok")]} | '
            f'{mark[r.get("pages_ok")]} | {r.get("prompt_tokens", 0)} | '
            f'{r.get("latency_s", 0)} с | ${r.get("cost_usd", 0):.3f} |'
        )

    flagged = [r for r in results if r.get("unverified_numbers")]
    if flagged:
        lines += ["", "## Числа без подтверждения в контексте", ""]
        for r in flagged:
            lines.append(f'- {r["id"]} (`{r["mode"]}`): {", ".join(r["unverified_numbers"])}')

    errors = [r for r in results if r.get("error")]
    if errors:
        lines += ["", "## Ошибки прогона", ""]
        for r in errors:
            lines.append(f'- {r["id"]} (`{r["mode"]}`): {r["error"]}')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Прогон вопросов через режимы поиска")
    parser.add_argument("--modes", default="router", help="режимы через запятую: full,router,vector")
    parser.add_argument("--limit", type=int, default=None, help="сколько вопросов взять")
    parser.add_argument("--model", default=None, help="переопределить модель ответа")
    parser.add_argument("--quick", action="store_true", help="три вопроса в режиме router")
    parser.add_argument("--ids", default=None, help="прогнать только эти вопросы, через запятую")
    parser.add_argument("--append", action="store_true",
                        help="дописать к сохранённым результатам вместо перезаписи")
    args = parser.parse_args()

    modes = ("router",) if args.quick else tuple(m.strip() for m in args.modes.split(","))
    limit = 3 if args.quick else args.limit

    print(f"Прогон: режимы {modes}, вопросов {limit or 'все'}, модель {args.model or config.MODELS['answer']}")
    ids = [i for i in (args.ids or "").split(",") if i.strip()] or None
    results = run(modes=modes, limit=limit, model=args.model, ids=ids)

    if args.append and RESULTS_JSON.exists():
        # Дозапись, а не перезапись: измеренное ранее стоило денег и
        # повторять его незачем. Совпадающие id и режим замещаются свежими.
        with io.open(RESULTS_JSON, encoding="utf-8") as f:
            previous = json.load(f)
        fresh = {(r["id"], r["mode"]) for r in results}
        results = [r for r in previous if (r["id"], r["mode"]) not in fresh] + results

    with io.open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with io.open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write(render_markdown(results))

    passed = sum(1 for r in results if r.get("passed"))
    cost = sum(r.get("cost_usd", 0) for r in results)
    print(f"\nИтог: {passed}/{len(results)} пройдено, потрачено ${cost:.2f}")
    print(f"Отчёт: {RESULTS_MD}")


if __name__ == "__main__":
    main()
# END_BLOCK_REPORT


# START_BLOCK_RESCORE
def rescore():
    """Пересчёт оценок по сохранённым ответам, без обращения к модели.

    Нужен, когда дефект найден в критерии, а не в системе: перегонять ответы
    заново значило бы платить за исправление собственной меры.
    """
    from types import SimpleNamespace

    with io.open(RESULTS_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    questions = {q["id"]: q for q in load_questions()}

    for row in rows:
        if row.get("error") or "answer" not in row:
            continue
        question = questions.get(row["id"])
        if not question:
            continue
        fake = SimpleNamespace(
            text=row["answer"],
            cited_pages=row.get("cited_pages") or [],
            unverified_numbers=row.get("unverified_numbers") or [],
            has_citations=bool(row.get("cited_pages")),
        )
        card = score(question, fake)
        row.update(card)
        row["passed"] = _passed(card)

    with io.open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    with io.open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write(render_markdown(rows))
    scored = [r for r in rows if not r.get("error")]
    print(f"пересчитано: {sum(1 for r in scored if r['passed'])}/{len(scored)} пройдено")
# END_BLOCK_RESCORE

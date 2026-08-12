"""Подстановка измеренной матрицы в README между маркерами."""

# FILE: eval/update_readme.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: перенести результаты прогона в README, чтобы матрица содержала измеренные значения, а не прочерки.
#   SCOPE: чтение eval/results.json, сборка таблицы, замена блока между маркерами MATRIX.
#   DEPENDS: M-EVAL
#   LINKS: M-EVAL, V-M-EVAL
#   INPUTS: eval/results.json
#   OUTPUTS: README.md
#   ROLE: SCRIPT
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   build_matrix - таблица режимов с долями пройденного, токенами, задержкой и ценой
#   main - подстановка таблицы в README между маркерами
# END_MODULE_MAP

import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results.json"
README = ROOT / "README.md"
BEGIN, END = "<!-- MATRIX:BEGIN -->", "<!-- MATRIX:END -->"


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def build_matrix(results: list) -> str:
    modes = list(dict.fromkeys(r["mode"] for r in results))
    model = next((r.get("model") for r in results if r.get("model")), "—")

    lines = [
        f"Модель ответа: `{model}`. Набор: {len({r['id'] for r in results})} вопросов.",
        "",
        "| Режим | Пройдено | Числа верны | Страницы верны | Медиана токенов | Медиана задержки | Цена набора |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode in modes:
        rows = [r for r in results if r["mode"] == mode]
        values = [r for r in rows if r.get("values_ok") is not None]
        pages = [r for r in rows if r.get("pages_ok") is not None]
        tokens = _median([r.get("prompt_tokens", 0) for r in rows])
        lines.append(
            f'| `{mode}` | {sum(1 for r in rows if r.get("passed"))}/{len(rows)} '
            f'| {sum(1 for r in values if r["values_ok"])}/{len(values)} '
            f'| {sum(1 for r in pages if r["pages_ok"])}/{len(pages)} '
            f'| {tokens:,}'.replace(",", " ")
            + f' | {_median([r.get("latency_s", 0) for r in rows])} с '
            f'| ${sum(r.get("cost_usd", 0) for r in rows):.2f} |'
        )

    # Экономия считается от медианы токенов полного контекста.
    full_rows = [r for r in results if r["mode"] == "full"]
    if full_rows:
        base = _median([r.get("prompt_tokens", 0) for r in full_rows]) or 1
        lines += ["", "Экономия контекста относительно полного режима:", ""]
        for mode in modes:
            if mode == "full":
                continue
            rows = [r for r in results if r["mode"] == mode]
            saved = 100 - 100 * _median([r.get("prompt_tokens", 0) for r in rows]) / base
            lines.append(f"- `{mode}`: {saved:.0f}%")

    lines += ["", f"Подробности по каждому вопросу: `eval/results.md`."]
    return "\n".join(lines)


def main():
    with io.open(RESULTS, encoding="utf-8") as f:
        results = json.load(f)

    text = io.open(README, encoding="utf-8").read()
    start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
    updated = text[:start] + "\n" + build_matrix(results) + "\n" + text[end:]
    io.open(README, "w", encoding="utf-8").write(updated)
    print(f"матрица обновлена: {README}")


if __name__ == "__main__":
    main()

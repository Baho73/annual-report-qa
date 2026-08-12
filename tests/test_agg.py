"""V-M-AGG: агрегаты и контрольные суммы.

Ключевой тест — контрольная сумма: она обязана поймать испорченные данные.
Без неё ошибка разбора становится уверенным враньём в ответе.
"""

import pytest

from report_qa import config
from report_qa.parse import (
    load_tables, compute_aggregates, checksum_segments, total_revenue, TOP_SEGMENTS,
)

RECORDS = load_tables() if config.TABLES_JSON.exists() else []

pytestmark = pytest.mark.skipif(not RECORDS, reason="нет data/tables_merged.json")


def test_total_revenue_prefers_confirmed_and_precise():
    """Из нескольких кандидатов берётся подтверждённый двумя путями и точный.

    В документе есть и округлённое 1441.0 из обзорной врезки (только зрение),
    и 1441.1 из финансового раздела (код и зрение независимо).
    """
    rec = total_revenue(RECORDS, "2025")
    assert rec is not None
    assert rec["v"] == pytest.approx(1441.1)
    assert rec.get("src") == "both" or rec.get("confirmed")


def test_checksum_reproduces_known_result():
    """Известный результат: 1630.9 против 1441.1, с коррекцией расхождение 0.007%."""
    c = checksum_segments(RECORDS, "2025")
    assert c["sum_raw"] == pytest.approx(1630.9, abs=0.05)
    assert c["intersegment_correction"] == pytest.approx(-189.7, abs=0.05)
    assert c["sum_adjusted"] == pytest.approx(1441.2, abs=0.05)
    assert c["delta_raw_pct"] == pytest.approx(13.17, abs=0.05)
    assert c["delta_pct"] <= config.THRESHOLDS["checksum_delta_pct"]
    assert c["ok"] is True


def test_checksum_catches_corrupted_data():
    """Потерянная строка сегмента поднимает флаг, а не проходит молча."""
    broken = [r for r in RECORDS
              if not (r.get("s") == "Городские сервисы"
                      and str(r.get("p")) == "2025"
                      and "выручк" in str(r.get("m", "")).lower())]
    c = checksum_segments(broken, "2025")
    assert c["ok"] is False, "контрольная сумма не заметила пропажу крупнейшего сегмента"


def test_all_top_segments_present():
    agg = compute_aggregates(RECORDS)
    found = {s["segment"] for s in agg["segments"]}
    assert found == set(TOP_SEGMENTS), f"не хватает сегментов: {set(TOP_SEGMENTS) - found}"


def test_growth_ranking_answers_the_question():
    """Вопрос «что росло быстрее» закрывается порядком, а не счётом модели."""
    agg = compute_aggregates(RECORDS)
    ranked = [s for s in agg["segments"] if s.get("yoy_pct") is not None]
    assert ranked[0]["segment"] == "Автономные технологии"
    assert ranked[1]["segment"] == "Персональные сервисы"
    assert ranked[-1]["segment"] == "Поисковые сервисы и ИИ"


def test_contributions_sum_to_total_growth():
    """Вклады в прирост в сумме дают общий прирост.

    Проверка сходимости: если вклад посчитан неверно, сумма разъедется.
    """
    agg = compute_aggregates(RECORDS)
    contrib = sum(s["contrib_growth_pct"] for s in agg["segments"]
                  if s.get("contrib_growth_pct") is not None)
    # «Прочие сервисы» не имеют сопоставимого прошлого периода в данных,
    # поэтому допуск шире формальной погрешности округления.
    assert contrib == pytest.approx(100, abs=5)


def test_every_aggregate_carries_page():
    """Каждое агрегированное значение прослеживается до страницы источника."""
    agg = compute_aggregates(RECORDS)
    assert agg["total_revenue_page"]
    for s in agg["segments"]:
        assert s["page"], f'нет страницы у сегмента {s["segment"]}'

"""V-M-UI: демонстрация поднимается и не падает на импорте.

Полноценный UI-тест требует запуска Streamlit; на прототипе достаточно
проверить, что модуль импортируется, вопросы-примеры на месте и разметка
не потеряна. Демо не должно падать на глазах у комиссии.
"""

import importlib.util
import pytest

from report_qa import config

streamlit_installed = importlib.util.find_spec("streamlit") is not None


@pytest.mark.skipif(not streamlit_installed, reason="streamlit не установлен")
def test_app_imports():
    import app  # noqa: F401


@pytest.mark.skipif(not streamlit_installed, reason="streamlit не установлен")
def test_samples_cover_task_questions():
    """В примерах есть все пять вопросов задания плюс проверка на отказ."""
    import app

    joined = " ".join(app.SAMPLES).lower()
    for marker in ("выручка", "росли быстрее", "риски", "чистая прибыль",
                   "инвестировать", "германии"):
        assert marker in joined, f"нет примера с «{marker}»"


def test_app_file_carries_markup():
    """Семантическая разметка — несущая структура, а не комментарий."""
    text = (config.BASE_DIR / "app.py").read_text(encoding="utf-8")
    for marker in ("START_MODULE_CONTRACT", "END_MODULE_CONTRACT",
                   "START_MODULE_MAP", "END_MODULE_MAP"):
        assert marker in text

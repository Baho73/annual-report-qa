"""M-CONFIG: пути, ключи, модели по ролям, пороги.

MODULE_CONTRACT:
    PURPOSE: единственный источник путей к данным, ключа OpenRouter, имён моделей
             по ролям и числовых порогов.
    SCOPE:   BASE_DIR, пути к PDF и артефактам, MODELS, THRESHOLDS, api_key().
    DEPENDS: none (корень графа).
"""

import os
from pathlib import Path

# START_BLOCK_PATHS
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BUILD_DIR = BASE_DIR / "build"
EVAL_DIR = BASE_DIR / "eval"

# Рабочий документ: Годовой отчёт МКПАО «Яндекс» за 2025, 201 страница.
PDF_PATH = DATA_DIR / "yandex_annual_report_2025.pdf"
# Контрольный пример: бизнес-рисков не содержит, нужен для теста на честность.
IFRS_PDF_PATH = DATA_DIR / "yandex_ifrs_fy2025.pdf"

SECTIONS_JSON = DATA_DIR / "sections.json"
TABLES_JSON = DATA_DIR / "tables_merged.json"
AGGREGATES_JSON = DATA_DIR / "aggregates.json"
INVENTORY_JSON = DATA_DIR / "inventory.json"
# END_BLOCK_PATHS

# START_BLOCK_MODELS
# Дефолт намеренно избыточен: сначала доказываем, что задача решается,
# оптимизация после. Порядок удешевления — сначала контекст, потом модель.
# ponytail: fast-варианты вдвое дороже и нужны только там, где пользователь ждёт
# ответ; в офлайн-подготовке скорость отклика не нужна.
MODELS = {
    "answer": "anthropic/claude-opus-5",
    "router": "google/gemini-2.5-flash",
    "vision": "anthropic/claude-opus-5",
    "embeddings": "BAAI/bge-m3",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
HTTP_TIMEOUT = 180  # секунд; любой исходящий HTTP только с таймаутом
# END_BLOCK_MODELS

# START_BLOCK_THRESHOLDS
THRESHOLDS = {
    # Расхождение суммы частей с итогом, выше которого поднимается флаг.
    "checksum_delta_pct": 0.5,
    # Сколько чанков отдаёт векторная ветка. Меньше — и проигрыш объяснялся бы
    # размером выборки, а не качеством поиска.
    "top_k": 8,
    # Ниже этого роутер расширяет набор разделов вместо сужения.
    "router_min_confidence": 0.6,
    # Допуск при сверке числа из ответа с эталоном (относительный).
    "number_tolerance_pct": 0.5,
}
# END_BLOCK_THRESHOLDS


# START_BLOCK_API_KEY
def api_key() -> str:
    """Ключ OpenRouter из окружения.

    Ошибка возникает при первом обращении к модели, а не при импорте: тесты
    разбора и агрегатов должны работать без ключа.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Не задан OPENROUTER_API_KEY. Экспортируйте ключ перед запуском: "
            "export OPENROUTER_API_KEY=sk-or-..."
        )
    return key
# END_BLOCK_API_KEY

"""M-CONFIG: пути, ключи, модели по ролям, пороги."""

# FILE: report_qa/config.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: единственный источник путей к данным, ключа OpenRouter, имён моделей по ролям и числовых порогов.
#   SCOPE: пути к PDF и артефактам, MODELS, THRESHOLDS, HTTP_TIMEOUT, api_key().
#   DEPENDS: none
#   LINKS: M-CONFIG, V-M-CONFIG
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   BASE_DIR - корень проекта, от него разрешаются все пути
#   DATA_DIR - каталог данных и артефактов разбора
#   BUILD_DIR - одноразовые скрипты и кэш vision-прохода
#   EVAL_DIR - вопросы с эталонами и прогон замера
#   PDF_PATH - рабочий документ: Годовой отчёт Яндекса 2025, 201 страница
#   IFRS_PDF_PATH - контрольный пример: бизнес-рисков не содержит
#   SECTIONS_JSON - разделы по встроенным закладкам
#   TABLES_JSON - числа в длинном формате с провенансом
#   AGGREGATES_JSON - приросты, доли, вклад в прирост, контрольные суммы
#   INVENTORY_JSON - опись объектов документа: таблицы, графики, инфографика
#   MODELS - модели по ролям: answer, router, vision, embeddings
#   OPENROUTER_URL - единая точка входа к моделям
#   HTTP_TIMEOUT - обязательный таймаут любого исходящего запроса
#   THRESHOLDS - пороги: расхождение контрольной суммы, top_k, уверенность роутера
#   api_key - ключ OpenRouter из окружения, ошибка при вызове, а не при импорте
# END_MODULE_MAP

import os
from pathlib import Path

__all__ = [
    "BASE_DIR", "DATA_DIR", "BUILD_DIR", "EVAL_DIR",
    "PDF_PATH", "IFRS_PDF_PATH",
    "SECTIONS_JSON", "TABLES_JSON", "AGGREGATES_JSON", "INVENTORY_JSON",
    "MODELS", "OPENROUTER_URL", "HTTP_TIMEOUT", "THRESHOLDS", "api_key",
]

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

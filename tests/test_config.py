"""V-M-CONFIG: пути от корня проекта, ключ только при обращении к модели."""

import os
import pytest

from report_qa import config


def test_paths_resolve_from_project_root_not_cwd(tmp_path, monkeypatch):
    """Пути абсолютны и не зависят от текущей директории."""
    monkeypatch.chdir(tmp_path)
    assert config.BASE_DIR.is_absolute()
    assert config.PDF_PATH.is_absolute()
    assert config.PDF_PATH.parent == config.DATA_DIR
    assert config.BASE_DIR.name == "test-4a"


@pytest.mark.skipif(not config.PDF_PATH.exists(),
                    reason="PDF не входит в репозиторий, ссылка на источник в README")
def test_working_document_exists():
    """Рабочий документ на месте.

    PDF весит 4.6 МБ и в репозиторий не коммитится. Артефакты разбора
    (sections.json, tables_merged.json) лежат в data/, поэтому демо и замер
    работают без исходника; повторный разбор требует скачать его по ссылке.
    """
    assert config.PDF_PATH.exists(), f"нет файла {config.PDF_PATH}"


def test_missing_key_raises_on_call_not_on_import(monkeypatch):
    """Отсутствие ключа ломает вызов модели, а не импорт модуля.

    Тесты разбора и агрегатов должны проходить без ключа.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        config.api_key()


def test_api_key_returns_value(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert config.api_key() == "sk-or-test"


def test_models_defined_for_all_roles():
    for role in ("answer", "router", "vision", "embeddings"):
        assert config.MODELS.get(role), f"не задана модель для роли {role}"


def test_thresholds_sane():
    assert 0 < config.THRESHOLDS["checksum_delta_pct"] < 5
    assert config.THRESHOLDS["top_k"] >= 5
    assert config.HTTP_TIMEOUT > 0

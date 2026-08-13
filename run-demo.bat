@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Ключ OpenRouter берём из профиля hh_answer, чтобы не хранить второй копией.
for /f "delims=" %%K in ('python -c "import json;print(json.load(open(r'D:\Python\hh_answer\user_profile.json',encoding='utf-8'))['openrouter_api_key'])"') do set OPENROUTER_API_KEY=%%K

if "%OPENROUTER_API_KEY%"=="" (
    echo [ОШИБКА] Не удалось прочитать ключ OpenRouter.
    echo Задайте вручную:  set OPENROUTER_API_KEY=sk-or-...
    pause
    exit /b 1
)

echo Ключ загружен: %OPENROUTER_API_KEY:~0,12%...
echo Запускаю демо на http://localhost:8501
echo Остановить: Ctrl+C в этом окне
echo.

set PYTHONUTF8=1
streamlit run app.py

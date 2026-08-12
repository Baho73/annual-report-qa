# /afk decisions journal

## 2026-08-12T14:28:03.551Z — T-001 M-CONFIG
- class: `reversible-act`
- context: -
- rationale: Единственный источник путей, моделей и порогов; обычная реализация контракта, единственный credible подход
- outcome: report_qa/config.py + tests/test_config.py, 6 тестов зелёные, коммит сделан

## 2026-08-12T14:30:16.599Z — T-002 M-NUM
- class: `reversible-act`
- context: -
- rationale: Критичный модуль: без нормализации знак теряется молча. Два бага пойманы тестами до коммита — порядок NFKC и сносок, разбор многоточечных чисел
- outcome: report_qa/parse.py блок нормализации + 36 тестов зелёные

## 2026-08-12T14:31:44.438Z — T-003 M-PARSE
- class: `reversible-act`
- context: -
- rationale: Закладки PDF дают готовую иерархию, парсер оглавления писать не нужно; фолбэк для документов без закладок оставлен минимальным
- outcome: 178 разделов в data/sections.json, покрытие 1-201 без дыр, 6 тестов зелёные


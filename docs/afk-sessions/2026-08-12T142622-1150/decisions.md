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


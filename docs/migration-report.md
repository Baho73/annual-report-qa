# Отчёт миграции GRACE 3 → GRACE 4

Дата: 2026-08-12. Проект: `D:\Python\test-4a`. CLI: grace v4.0.4.

## Инвентарь источников

| Legacy-источник | Назначение в GRACE 4 | Статус |
|---|---|---|
| `docs/requirements.xml` | `.grace/context/requirements.xml` | перенесён, структура приведена к `GraceRequirements`: use cases свёрнуты в Goals/Users/Constraints, тест-матрица вопросов сохранена блоком `QuestionMatrix`, список отложенного — `OutOfScope` с триггерами |
| `docs/technology.xml` | `.grace/context/technology.xml` | перенесён, добавлены `Models`, `RetrievalStrategies`, `RejectedTechnology` |
| `docs/knowledge-graph.xml` | `.grace/graph/{index,prep,answer,eval}.xml` | 15 модулей разложены по трём графовым документам: подготовка, ответ, замер |
| `docs/development-plan.xml` | `.grace/verification/{index,prep,answer,eval}.xml` + `.grace/changes/active/C-001/` | планы верификации стали `V-M-*` записями со сценариями; порядок сборки стал задачами `T-001…T-014` |
| `CLAUDE.md` (проектные правила) | `.grace/context/principles.xml` | восемь проектных принципов добавлены к трём базовым |
| — | `.grace/context/deployment.xml`, `ux-guidelines.xml` | созданы заново, в GRACE 3 отсутствовали |
| `docs/*.md` (architecture, contradictions, document-integrity, improvement-techniques) | остаются на месте | это рабочие документы защиты, а не GRACE-артефакты; миграции не подлежат |

Новый модуль, которого не было в GRACE 3: `M-NUMCHECK` — проверка чисел готового ответа против поданного контекста.

## Бэкап

- Копия всех legacy XML: `.migration-backup/` (вне cleanup-набора).
- Git-коммит `d6971d2` содержит полное состояние до миграции.

## Валидация

| Проверка | Результат |
|---|---|
| `grace lint --path . --assertions current` | 0 ошибок, 0 предупреждений, 15 XML-артефактов |
| `grace status --path .` | `projectKind: grace4`, integrity 0 ошибок |
| Контекстных артефактов | 5 |
| Модулей графа | 15 |
| Записей верификации | 15 |
| Активных изменений | 1 (`C-001`, spec approved, plan approved, 14 задач) |

Исправления по ходу валидации: `Applicability` в deployment и ux-guidelines приведён к `applicable`; корневой тег `GraceUXGuidelines`; блоки `TestFiles` убраны, поскольку ссылались на ещё не созданные файлы (вернутся вместе с кодом); идентификатор бандла приведён к `C-001`; множественные зависимости задач записаны вложенными тегами вместо перечисления через запятую.

## Cleanup

**Не выполнялся.** Legacy `docs/*.xml` остаются нетронутыми: отдельного явного одобрения на удаление не запрашивалось и не давалось. Файлы дублируются в `.migration-backup/` и в git-истории.

## Незакрытое

- Derived state `unexplained-observed-drift`: в проекте есть файлы (`build/`, `data/`), не описанные графом. Ожидаемо для стадии до написания кода продукта, снимется по мере появления модулей.
- `TestFiles` в записях верификации будут возвращены по мере создания тестов.

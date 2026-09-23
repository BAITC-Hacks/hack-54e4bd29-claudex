# MedSignal Pilot Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Довести существующий MedSignal до воспроизводимого, защищённого и измеримо проверенного аналитического пилота.

**Architecture:** Incremental hardening существующего modular monolith. Сохранить принятые pipeline, scopes, Signal/Incident/Audit и Scenario; исследовательский pilot постепенно подключать через порты после проверки качества.

**Tech Stack:** FastAPI, PostgreSQL/Alembic, ClickHouse, Redis/Celery, Keycloak, Next.js, scikit-learn, Docker Compose, GitHub Actions.

**Spec:** ../specs/2026-09-23-pilot-consolidation-design.md

## Global Constraints

Все ограничения из spec обязательны для четырёх дочерних планов. Source read-only;
принятые migrations immutable; raw medical data и secrets не попадают в Git/CI;
никаких fake mappings; неизвестная полнота не превращается в нулевой поток;
STALE не создаёт operational forecast alerts; никаких обещаний освобождения коек.
Документ — предложение реализации по запросу пользователя, не отчёт о выполнении.

## Review Focus

1. Новый hash при перекрытии событий не должен удваивать факты — Data Task D1.
2. Отзыв mapping не должен оставлять scoped-доступ через cache — Data Task D2.
3. Пропавшая поставка не должна превращаться в нулевой спрос — Model Task M1.
4. Подбор порогов после просмотра test не должен считаться независимой оценкой — Model Task M2.
5. Повтор worker после записи результата не должен дублировать Forecast/Signal/Audit — Release Task R1.

## Планы и последовательность

| Пакет | План | Зависимости | Независимый результат |
|---|---|---|---|
| F — foundation repair | [01-reproducibility](2026-09-23-01-reproducibility.md) | Нет | Чистые сборки и CI обоих режимов, актуальные claims |
| D — data readiness | [02-data-readiness](2026-09-23-02-data-readiness.md) | F | Контроль поставок, mappings, честная completeness/freshness |
| M — model evidence | [03-model-evidence](2026-09-23-03-model-evidence.md) | F; real run требует D и новой истории | Повторяемая оценка с правом отказать в допуске |
| R — integration/release | [04-integration-release](2026-09-23-04-integration-release.md) | F; R1/R2 требуют D/M; R3/R4 можно готовить раньше | Основной защищённый workflow и acceptance evidence |

~~~mermaid
flowchart LR
  F[Воспроизводимость] --> D[Поставки и mappings]
  F --> M[Evaluation harness]
  O[Владелец данных: поставки и справочники] --> D
  D --> E[Новый независимый test]
  M --> E
  E --> G{Quality gate}
  G -->|PASS| I[Интеграция operational alerts]
  G -->|FAIL / INSUFFICIENT| A[Описательная аналитика и research]
  F --> H[Hardening и performance]
  I --> V[Shadow pilot и acceptance]
  H --> V
  A --> V
~~~

## Первая итерация

- [ ] F1: воспроизвести build/test в чистом окружении; не исправлять права через ослабление security.
- [x] F2: включить monitoring/pilot tests и проверки standalone Compose в CI.
- [x] F3: устранить противоречия claims, roadmap и target feasibility.
- [ ] D1: описать договор поставки, запросить owner evidence, реализовать контроль повторов и пересечений на synthetic fixtures.
- [ ] M1: оформить независимый evaluation harness, не переобучать бесконечно на уже просмотренном test.

Эти задачи не требуют новых реальных медицинских данных. Запрос владельцу данных
готовится в документе; его отправка другому человеку требует отдельного поручения.

## Gate register

| Gate | Что считается выполнением | Если входов нет |
|---|---|---|
| G0 Build | Clean install, backend/frontend/pilot tests, lint/types/build/import-linter | NOT TESTED с причиной среды |
| G1 Delivery | Подтверждённые semantics, целостность, повтор/overlap handling | EXTERNAL DEPENDENCY для владельца |
| G2 Identity | Approved mapping, projection consistency, scope/cache negative tests | Unmapped остаётся закрытым от restricted scopes |
| G3 Model | Утверждённая policy + новый sealed test + все метрики gate | POLICY_NOT_APPROVED / INSUFFICIENT_DATA / FAIL |
| G4 Workflow | Реальные OIDC роли, concurrent/retry E2E, audit atomicity | Operational alerts остаются выключенными |
| G5 Operations | TLS/perimeter, restore, monitoring, measured performance | EXTERNAL DEPENDENCY либо FAIL, без заявления production-ready |
| G6 Pilot | Процессный владелец оценил shadow mode и подписал operational admission | Продолжение descriptive/research режима |

Код может быть готов при G3 FAIL: это корректный результат исследования. Full release
не объявляется на основании одного процента точности или наличия deployment template.

## Контрольные результаты

1. Одна инструкция запуска с двумя явно названными режимами: основной и historical research.
2. Одна версия сущностей Forecast/Signal/Incident/Action/Audit; без второго production backend.
3. Каждая метрика имеет период, источник, watermark и ограничения.
4. Нет несопоставленных hospital signals или недоказанной исторической динамики очереди.
5. Отчёт о модели отделяет ошибку count forecast от полезности предупреждений.
6. Обновлённый acceptance report содержит фактически выполненные проверки текущего commit.

## Организация выполнения

Каждая задача дочернего плана имеет собственный тестовый результат и небольшой commit.
Для кодовых работ создать изолированную ветку/worktree по superpowers:using-git-worktrees.
Не переключать/сбрасывать чужие изменения, не создавать параллельный Compose на тех же портах/volumes.
Плановые commits являются инструкциями исполнителю; этот этап планирования ничего не пушит.

Предпочтительно последовательное native execution с независимым review security,
data semantics и model evaluation перед объединением. D и M содержат общие contracts,
поэтому параллельное редактирование этих интерфейсов не ускорит безопасную интеграцию.

## Self-review

- [x] Все шесть задач из предыдущего обсуждения разложены в F/D/M/R.
- [x] Новые данные, справочники и production infrastructure выделены как внешние зависимости.
- [x] Для каждой существенной ошибки из Review Focus есть владеющая задача.
- [x] Полнота модели не обещана заранее; есть отрицательные исходы gate.
- [x] Новые номера migrations не конфликтуют с существующими 0001–0006/001–005.
- [x] Исходные datasets и текущие рабочие volumes не используются для destructive tests.
- [x] План не начинает реализацию и не утверждает прохождение runtime tests.


## Execution checkpoint — 23.09.2026

F2/F3 implementation is reviewed and committed through 7cdfe3d. F1 native checks
passed, but the full build gate remains incomplete: Docker execution and external
CI are NOT TESTED. See [current evidence](../../acceptance/PILOT_BASELINE.md).
D/M/R have not started. No production readiness is inferred from this checkpoint.

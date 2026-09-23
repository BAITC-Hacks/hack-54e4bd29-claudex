# MedSignal Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Восстановить воспроизводимую проверку основного приложения и нового local pilot.

**Architecture:** Существующие CI jobs и Compose profiles; отдельный CI job для локального пилота, общие инженерные правила. Исправления baseline не меняют поведение authentication и аналитики.

**Tech Stack:** GitHub Actions, Python 3.12, pytest, Ruff/mypy/import-linter, npm ci, Next.js/Vitest, Docker Compose.

**Spec:** ../specs/2026-09-23-pilot-consolidation-design.md

## Global Constraints

SOURCE DIRECTORY = READ ONLY. Нет production code changes вне обнаруженных baseline defects.
Не переписывать accepted migrations. Никаких секретов/реальных datasets в CI.
Не применять AUTH_TEST_MODE вне local/test. Не удалять текущие Compose volumes.

## Review Focus

1. Зависимость есть в lockfile, но отсутствует локально — F1 clean install.
2. Docker недоступен по правам — F1 фиксирует NOT TESTED, не отключает controls.
3. Pilot без модели — F2 проверяет 503 без фиктивных результатов.
4. Pilot зависит от непоставленного пакета — F2 isolated job с явным requirements.
5. Старый отчёт выглядит текущей гарантией — F3 привязывает evidence к commit/date.

## File map

| Файл | Ответственность |
|---|---|
| .github/workflows/ci.yml | Проверки всех исполняемых модулей |
| Makefile | Те же команды для локального исполнителя |
| pilot/requirements-dev.txt — новый | Зависимости tests/lint local pilot |
| pilot/api.py, ml/monitoring.py | Только найденные lint/type defects на F2 |
| tests/monitoring/test_monitoring.py | Проверки модели и replay |
| README.md, docs/LOCAL_PILOT.md, docs/ROADMAP.md | Режимы и реальные ограничения |
| docs/data/TARGET_FEASIBILITY.md, data_pipeline/audit/target_analysis.py | Корректная оценка target availability |
| docs/acceptance/PILOT_BASELINE.md — новый | Воспроизводимый baseline evidence |

## Task F1: Clean baseline и классификация failures

**Files:** modify package.json/package-lock.json только если clean npm ci доказывает дефект;
create docs/acceptance/PILOT_BASELINE.md; read docker-compose*.yml, backend/pyproject.toml.

**Interfaces:** consumes current commit + lockfiles; produces baseline report с командами,
exit codes, commit, tool versions, PASS/FAIL/NOT TESTED.

- [ ] Зафиксировать git status и hash, runtime versions; не читать .env в tool output.
- [ ] В изолированном checkout выполнить команды из корня; Windows поддерживается
  через Docker и npm.cmd, без предположения о наличии host Python.

~~~powershell
git status --short
git rev-parse HEAD
docker version
docker compose config --quiet
docker compose -f docker-compose.pilot.yml config --quiet
Push-Location frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
Pop-Location
~~~

- [ ] Проверить основной Python-контур через существующие targets. Если Docker
  недоступен по permissions, не запускать альтернативный небезопасный daemon.
  Исполнить эти проверки в доступном CI runner и записать ссылку на run.

~~~bash
make test-backend
make test-ml
make lint
PYTHONPATH=.:backend lint-imports --config .importlinter
~~~

- [ ] При настоящем code defect сначала воспроизвести конкретным existing test или
  новым regression test; при stale node_modules восстановить npm ci, не менять TS config.
- [ ] Записать отдельно текущий результат и historical Phase 8 evidence.
- [ ] Commit только baseline repairs и report: fix: restore reproducible project checks.

**Приёмка:** ошибок кода нет либо они перечислены как FAIL; ограничения среды не
названы PASS. Leaflet import разрешается после clean install из lockfile.

## Task F2: Pilot tests становятся обязательной частью CI

**Files:** modify .github/workflows/ci.yml, Makefile, tests/monitoring/test_monitoring.py,
pilot/Dockerfile, docker-compose.pilot.yml;
create pilot/requirements-dev.txt; lint/format pilot и ml/monitoring.py без смены алгоритма.

**Interfaces:** existing ml.monitoring.aggregate/features/samples/alert_for и
pilot.api.create_app сохраняют публичный контракт; CI produces junit-monitoring.xml.

- [x] Запустить существующие tests/monitoring в чистом Python 3.12 job, подтвердить
  реальную ошибку при её наличии. Не писать искусственно красный тест для YAML.
- [x] Добавить requirements-dev, использующий production requirements пилота:

~~~text
-r requirements.txt
pytest==8.3.*
httpx==0.28.*
ruff==0.8.*
~~~

- [x] Добавить отдельный job monitoring; env PYTHONPATH указывает на repository root.
  Команды job:

~~~bash
python -m pip install -r pilot/requirements-dev.txt
ruff check pilot ml/monitoring.py tests/monitoring --config backend/pyproject.toml
ruff format --check pilot ml/monitoring.py tests/monitoring --config backend/pyproject.toml
python -m pytest tests/monitoring -q --junitxml=junit-monitoring.xml
docker compose -f docker-compose.pilot.yml config --quiet
~~~

- [x] Расширить existing API test, проверив fail-closed mutations и отсутствие
  выдуманных predictions при отсутствующем bundle:

~~~python
def test_missing_model_never_returns_fake_monitor(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/pilot/monitor").status_code == 503
        assert client.post(
            "/api/pilot/replay", json={"action": "step"}
        ).status_code == 403
~~~

- [x] Повторить пилотные tests и existing ml/tests. Убедиться, что основной ML job
  продолжает проверять весь ml, а не только старую подпапку.
- [x] Добавить development target пилотного image с requirements-dev и synthetic
  tests/monitoring; сохранить runtime target последним/default и непривилегированным.
  Добавить monitoring-tests service в docker-compose.pilot.yml с profiles tools,
  build target development, без ports и без source datasets mounts. Его command:
  python -m pytest tests/monitoring -q.
- [x] Добавить make test-monitoring с командой
  docker compose -f docker-compose.pilot.yml run --rm --no-deps monitoring-tests.
  make test должен включать backend, ML, pipeline, monitoring,
  frontend и security/contracts, не создавать ложное название «все» для поднабора.
- [x] Commit: ci: include local monitoring pilot in regression checks.

**Приёмка:** поломка tests/monitoring блокирует merge; CI не скачивает real medical data,
не обучает на реальных выгрузках и не обращается к external LLM/API.

## Task F3: Согласовать документацию и генератор target audit

**Files:** modify README.md, docs/ROADMAP.md, docs/LOCAL_PILOT.md,
docs/data/TARGET_FEASIBILITY.md, docs/data/DATA_AUDIT_REPORT.md,
data/audit/medsignal_audit_summary.json, data_pipeline/audit/target_analysis.py;
test tests/audit/test_target_semantics.py — новый.

**Interfaces:** audit output сохраняет поле target_candidates; semantic availability
для queue forecast требует repeated verified snapshots, refusal ratio — aligned population.
Добавить pure функция:

~~~python
def assess_temporal_target(
    target: str, *, verified_snapshot_count: int,
    denominator_aligned: bool
) -> tuple[str, str]:
    if target == "queue_size(t+n)" and verified_snapshot_count < 2:
        return ("NOT AVAILABLE", "NO_VERIFIED_SNAPSHOT_HISTORY")
    if target == "refusal_rate" and not denominator_aligned:
        return ("NOT AVAILABLE", "DENOMINATOR_NOT_ALIGNED")
    return ("PARTIALLY AVAILABLE", "REQUIRES_COVERAGE_REVIEW")
~~~

- [x] Написать regression test против прежней ложной доступности:

~~~python
def test_one_snapshot_is_not_queue_forecast_history():
    from data_pipeline.audit.target_analysis import assess_temporal_target
    assert assess_temporal_target(
        "queue_size(t+n)", verified_snapshot_count=1,
        denominator_aligned=False
    ) == ("NOT AVAILABLE", "NO_VERIFIED_SNAPSHOT_HISTORY")
~~~

- [x] Run python -m pytest tests/audit/test_target_semantics.py -q; expected FAIL
  до появления helper.
- [x] Подключить helper к существующему target analysis; неизвестная семантика
  не считается подтверждённой. Один срез остаётся доступен для descriptive count.
- [x] Добавить аналогичный assert для refusal_rate; run python -m pytest tests/audit -q.
- [x] Обновить human/machine summaries как датированную semantic correction, сохранив
  исходные fingerprint/row count; не переписывать историю измерений и min/max вручную.
- [x] README описывает основной защищённый продукт и отдельный historical research
  pilot, actual model и deferred features; roadmap ссылается на текущие документы.
- [x] Commit: docs: align target feasibility and pilot readiness claims.

**Приёмка:** повторный audit не восстанавливает неверный queue forecast AVAILABLE;
читатель видит, что рост направлений не является доказанной перегрузкой.

## Execution status — 23.09.2026

Implementation: F1 baseline repair, F2 CI integration and F3 semantic correction are
committed in codex/pilot-reproducibility through 7cdfe3d. Independent task and final
integration reviews approved the source/documentation changes.

Native verification: backend 408 passed/2 skipped; root 207 passed/1 skipped;
monitoring 8 passed; frontend 17 passed and production build passed on Node 24;
12 architecture contracts kept. F3 added 24 regression cases including the real CLI.

Execution acceptance remains partial: Node 22/container builds stalled in the host
Docker runtime; aggregate make test and external GitHub CI/required-check enforcement
are NOT TESTED. These unchecked runtime gates are not waived. Exact commands, exit
codes, evidence identities and remaining gates: ../../acceptance/PILOT_BASELINE.md.

No downstream D/M/R implementation or production admission is included.

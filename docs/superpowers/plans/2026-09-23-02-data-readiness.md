# MedSignal Data Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Принимать последовательные поставки без удвоения событий и применять подтверждённые mappings к аналитике с корректным data scope.

**Architecture:** Расширить существующие DataImport/ImportService, а не создавать второй pipeline. PostgreSQL хранит delivery/mapping decisions; ClickHouse хранит опубликованные facts и версию безопасной mapping projection. Общей distributed transaction нет: publication выполняется после verification.

**Tech Stack:** Existing data_pipeline, FastAPI, SQLAlchemy/Alembic, PostgreSQL, ClickHouse, pytest.

**Spec:** ../specs/2026-09-23-pilot-consolidation-design.md

## Execution status — 2026-09-23

D1–D3 implementation and native regression checks are complete. Independent review findings are fixed and rechecked. Real PostgreSQL clean/upgrade/locking and ClickHouse projection execution remain NOT TESTED; owner supply semantics/mappings remain EXTERNAL DEPENDENCY. Checklist steps that combine implementation with live checks are not marked complete solely from native tests.

Actual commands, results and outstanding gates: [consolidation report](../../acceptance/PILOT_CONSOLIDATION_IMPLEMENTATION.md). Unchecked original steps remain a conservative combined acceptance checklist, not a claim that the corresponding code is absent.

## Global Constraints

SOURCE DIRECTORY = READ ONLY. Dataset allowlist остаётся referrals/waiting/refusals/treated.
Не угадывать snapshot/reporting dates; не исправлять оригинальные файлы.
HMAC до analytical storage. Нет fuzzy/fake mapping и дедупликации по одному
hospitalization_code: audit уже обнаружил повторения этого поля.
Принятые migrations неизменны. Любая новая схема — отдельная revision от фактического head.

## Review Focus

1. Новый file hash содержит прежний период — D1 блокирует unsupported overlap.
2. Не пришёл один из нескольких файлов — D1 не объявляет delivery complete.
3. Код одинаков в разных источниках/ролях организации — D2 identity_space обязателен.
4. Отозванная mapping остаётся в Redis/ClickHouse — D2/D3 fail-closed и versioned cache.
5. Load timestamp новее событий — D3 не делает данные CURRENT автоматически.

## File map

| Файл | Ответственность |
|---|---|
| backend/app/shared/delivery.py — новый | Framework-free delivery contracts и statuses |
| backend/app/models/delivery.py — новый | Persistent manifest, parts, completeness, approval |
| backend/app/business/ingestion/delivery.py — новый | Completeness/overlap/publication policy |
| backend/app/repositories/delivery.py — новый | Delivery queries, reservations и locking |
| backend/app/business/ingestion/service.py | Связь с existing file-level DataImport |
| backend/app/cli/data.py | CLI manifest и approved registered references |
| backend/app/models/mapping.py, repositories/mapping.py | Alias identity и mapping revisions |
| backend/app/business/mapping/service.py — новый | Approve/revoke/publish с audit |
| backend/app/shared/mapping.py — новый | Нейтральный MappingSnapshot contract |
| backend/app/repositories/clickhouse_mapping.py — новый | Verified projection publication |
| backend/app/repositories/clickhouse_analytics.py | Применение mapping до scoped aggregation |
| backend/app/business/analytics/service.py | Mapping watermark и cache isolation |
| docs/data/DATA_SUPPLY_CONTRACT.md — новый | Вопросы владельцу и принятые ответы |

## Task D1: Delivery contract, completeness и overlap protection

**Files:** create shared/delivery.py, models/delivery.py, repositories/delivery.py,
business/ingestion/delivery.py, docs/data/DATA_SUPPLY_CONTRACT.md;
modify business/ingestion/service.py, business/ports.py, repositories/unit_of_work.py,
cli/data.py; create backend/alembic/versions/20260923_delivery_manifest.py,
backend/tests/unit/test_delivery_policy.py, backend/tests/integration/test_delivery_import.py.

**Interfaces:** consumes existing DataImport and SourceFileRef. Proposed delivery
contract contains only operational metadata:

~~~python
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

class DeliveryMode(StrEnum):
    DELTA = "DELTA"
    SNAPSHOT = "SNAPSHOT"
    REPLACEMENT = "REPLACEMENT"

@dataclass(frozen=True)
class DeliveryManifest:
    delivery_id: str
    dataset_type: str
    source_system: str
    schema_version: str
    mode: DeliveryMode
    period_start: date | None
    period_end: date | None
    snapshot_date: date | None
    file_hashes: tuple[str, ...]
    expected_rows: int | None
    contract_version: str

def assess_delivery(
    manifest: DeliveryManifest, *, received_hashes: frozenset[str],
    overlaps_published_period: bool, contract_approved: bool
) -> tuple[bool, str]:
    if not contract_approved:
        return False, "CONTRACT_NOT_APPROVED"
    if set(manifest.file_hashes) != received_hashes:
        return False, "PARTS_MISMATCH"
    if manifest.mode == DeliveryMode.REPLACEMENT:
        return False, "REPLACEMENT_NOT_SUPPORTED"
    if manifest.mode == DeliveryMode.SNAPSHOT:
        if manifest.snapshot_date is None:
            return False, "UNKNOWN_SNAPSHOT_DATE"
    elif manifest.period_start is None or manifest.period_end is None:
        return False, "UNKNOWN_PERIOD"
    elif manifest.period_start > manifest.period_end:
        return False, "INVALID_PERIOD"
    if overlaps_published_period:
        return False, "OVERLAPPING_DELIVERY"
    return True, "READY"
~~~

REPLACEMENT на этой итерации возвращает REPLACEMENT_NOT_SUPPORTED: наличие enum не
означает реализованную автоматическую коррекцию опубликованных facts.
SNAPSHOT requires owner-confirmed snapshot_date; same supplied snapshot
under different file hash is an overlap requiring explicit replacement semantics.

- [ ] Подготовить DATA_SUPPLY_CONTRACT: cadence, timezone, effective/reporting period,
  delta/full snapshot/correction, stable keys, part manifest, complete-through date,
  holiday/closure evidence, code dictionaries. Пометить ответы, которых нет, как
  EXTERNAL DEPENDENCY. Не отправлять документ владельцу без поручения.
- [ ] Написать failing policy tests, включая:

~~~python
def test_changed_hash_does_not_authorize_overlapping_events():
    from datetime import date
    from app.shared.delivery import DeliveryManifest, DeliveryMode
    from app.business.ingestion.delivery import assess_delivery
    delivery = DeliveryManifest(
        "synthetic-2", "REFERRALS", "IS_BG", "v1", DeliveryMode.DELTA,
        date(2025, 1, 1), date(2025, 1, 31), None, ("b" * 64,), 2, "test-v1"
    )
    assert assess_delivery(
        delivery, received_hashes=frozenset({"b" * 64}),
        overlaps_published_period=True, contract_approved=True,
    ) == (False, "OVERLAPPING_DELIVERY")
~~~

- [ ] Run python -m pytest backend/tests/unit/test_delivery_policy.py -q; expected FAIL.
- [ ] Implement ordered policy. Persist delivery+parts, approved contract version,
  DataImport linkage и published status; UTC timestamps. Сравнить manifest с
  фактическими hashes/row counts и reviewed period semantics; manifest не считается
  доказательством только потому, что его прислал клиент.
- [ ] Reserve source/dataset period транзакционно: per-source lock и overlap query
  должны предотвращать две concurrent непересекающимися объявленные поставки с
  одинаковым периодом. File-level idempotency dataset_type+file_hash сохраняется.
- [ ] На partial failure сохранить file results для recovery, но не публиковать
  незавершённую delivery в operational forecasts. Обновить analytical publication
  filter/metadata: partial results разрешены только с явной маркировкой в quality view.
- [ ] Старые принятые импорты остаются видимыми исторически; не присваивать им
  подтверждённую полноту без evidence.
- [ ] Test retry after crash, renamed same hash, changed hash overlap, missing part,
  same snapshot changed contents, no period, concurrent reservation. Сверить counts
  PG/CH в isolated integration DB; failed delivery не видна как current.
- [ ] Migration clean/upgrade/check, затем commit: feat: validate delivery completeness and overlap.

**Приёмка:** следующий файл не удваивает старый период молча; без owner semantics
получается понятный отказ/ожидание, а не выдуманный ingestion API.

## Task D2: Подтверждённые mappings и безопасная публикация версии

**Files:** modify models/mapping.py, repositories/mapping.py, business/ports.py,
repositories/unit_of_work.py, security/permissions.py, models/enums.py;
create shared/mapping.py, business/mapping/__init__.py, business/mapping/service.py,
business/mapping/ports.py, repositories/clickhouse_mapping.py, cli/mapping.py;
create backend/alembic/versions/20260923_mapping_versions.py,
database/clickhouse/migrations/006_mapping_projection.sql;
test backend/tests/unit/test_mapping_service.py,
backend/tests/integration/test_mapping_publication.py.

Если при исполнении 006 занят — добавить следующий свободный DDL, не перезаписывать.
Revision ID Alembic сгенерировать от actual head. В filenames указан предполагаемый
новый документ миграции, а не разрешение менять accepted history.

**Interfaces:** proposed neutral contract:

~~~python
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class ApprovedOrganizationMapping:
    identity_space: str
    source_key: str
    hospital_id: UUID

@dataclass(frozen=True)
class MappingSnapshot:
    version: str
    organizations: tuple[ApprovedOrganizationMapping, ...]
    digest: str
~~~

Business methods:
approve(context, alias_id: UUID, hospital_id: UUID, evidence_ref: str,
expected_version: int) -> str;
revoke(context, alias_id: UUID, reason: str, expected_version: int) -> str;
publish(context, version: str) -> MappingSnapshot.
Repository выполняет queries; правила и audit находятся в service.

- [ ] Написать ADR о versioned mapping projection и effective scope; это осознанное
  новое решение, а не скрытая смена ADR-0008 или signal dedup.
  Proposed file: docs/ADR/0019-versioned-mapping-projection.md; проверить свободный
  номер при исполнении, добавить ссылку в docs/ADR/README.md.
- [ ] Написать tests: неизвестный hospital → 404; normal user → denied;
  одинаковый source key в REFERRALS:RECEIVING и WAITING:DESTINATION не означает merge;
  conflicted mappings → REVIEW_REQUIRED; stale expected_version → conflict.
- [ ] Ввести identity_space из известных ролей source columns. Existing
  source_system+normalized_value недостаточен для различения кодовых пространств.
  Legacy ambiguous aliases получают LEGACY_UNRESOLVED и не попадают в approved projection.
- [ ] Добавить version/history/evidence/actor для approval/revocation. Только
  OFFICIAL_REFERENCE или MANUAL_APPROVED; decision+audit одной PG transaction.
  Region mapping аналогичен; profile mapping не активировать без официального
  справочника и определённой canonical dimension.
- [ ] CH projection имеет явные version, identity_space, source_key, hospital_id.
  Ключ однозначен в версии. Записать candidate version, проверить count+digest,
  затем атомарно сменить active version в PG. Crash до смены указателя оставляет
  предыдущую версию; повтор publication детерминирован и не удваивает projection.
- [ ] Revocation немедленно запрещает прежнее scope entitlement в PG; до
  подтверждённой новой CH version dependent scoped queries fail closed.
  Не продолжать обслуживать cached старое разрешение.
- [ ] Запустить integration tests с fault injection на каждой границе публикации,
  clean/upgrade migrations, then commit: feat: publish approved mapping versions.

**Приёмка:** можно объяснить, кто и на основании чего связал source identity с Hospital;
отказ ClickHouse не превращается в расширенный доступ к данным.

## Task D3: Применить mapping/completeness в аналитике и freshness

**Files:** modify repositories/clickhouse_analytics.py, repositories/analytics_metadata.py,
business/analytics/service.py, shared/analytics_contracts.py, schemas/analytics.py,
frontend/src/features/analytics/types.ts,
frontend/src/features/analytics/components/data-freshness-badge.tsx;
test backend/tests/unit/test_analytics_service.py,
backend/tests/integration/test_clickhouse_analytics.py,
frontend/src/features/analytics/components/analytics-components.test.tsx.

**Interfaces:** query metadata/cache include mapping_version and published delivery
watermark; freshness includes event_period, confirmed_complete_through,
source_load_date, last_import, cadence_known, completeness.
Existing period/source/generated_at/limitations fields remain compatible.

- [ ] Write tests before query changes: historical unmapped fact becomes visible to
  correct hospital after approved mapping; another hospital still cannot see it.
  Revocation removes access despite a warm cache. Scoped HEALTH_AUTHORITY must not
  gain global access just from its role when effective policy lacks global grant.
- [ ] Resolve canonical ID through exact approved projection before aggregation
  and apply scope to resolved ID. Preserve unmatched facts for permitted global
  governance views. Same source name in another identity_space must not join.
- [ ] Add mapping_version to cache key; reject missing verified active version for
  dependent restricted queries. Build equality tests: sum(daily)==count(facts)
  under the same period, publication watermark, mapping version and scope.
- [ ] Source load timestamp alone must not mark Q1 2025 CURRENT. Unknown cadence →
  UNKNOWN; incomplete delivery visibly PARTIAL with forecast gate unavailable.
  Snapshot age only calculated if snapshot semantics approved, otherwise null with reason.
- [ ] UI tests cover unknown freshness, incomplete mapping, suppressed values,
  and mapping publication unavailable; no raw rows in API.
- [ ] Run targeted backend/CH/frontend tests; update docs/data/ORGANIZATION_MAPPING.md,
  docs/analytics/CACHE_STRATEGY.md and docs/analytics/METRIC_DEFINITIONS.md.
- [ ] Commit: feat: apply mapping versions and delivery completeness to analytics.

**Приёмка:** один и тот же факт не исчезает из GLOBAL analytics из-за NULL Hospital;
restricted users видят только подтверждённую область; dates не меняют смысл.

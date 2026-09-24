# MedSignal — сопоставление организаций, регионов и профилей

## 1. Задача

Data Audit показал, что выгрузки распадаются на две группы по
идентификатору медицинской организации, и между группами нет ни одного
общего значения.

| Группа | Как названа организация | Выгрузки |
|---|---|---|
| 1 | полное юридическое наименование | пролеченные случаи, направления, отказы |
| 2 | четырёхсимвольный код | очередь |

Внутри первой группы наименования пересекаются на 1 362 из 1 381.
Это наблюдение не подтверждает соответствие canonical Hospital: нужна
проверка системы-источника, роли столбца и evidence. Между группами пересечение нулевое.

То же с регионами: очередь использует числовые коды, отказы — наименования.

## 2. Как устроено хранение

Три таблицы PostgreSQL одинакового вида:

| Таблица | Каноническая ссылка |
|---|---|
| `organization_aliases` | `hospital_id` |
| `region_aliases` | `region_id` |
| `profile_aliases` | `canonical_profile_id` |

Каждая запись хранит значение из источника, его нормализованный вид,
систему-источник, состояние сопоставления и способ подтверждения.

| Состояние | Смысл |
|---|---|
| `UNMAPPED` | значение встречено, сопоставление не выполнено |
| `MAPPED` | сопоставление подтверждено |
| `REVIEW_REQUIRED` | требуется решение человека |

| Способ | Смысл |
|---|---|
| `OFFICIAL_REFERENCE` | официальный справочник |
| `MANUAL_APPROVED` | решение человека |

Способа «автоматически по похожести» не существует, и добавлять его
нельзя. Склейка двух наименований меняет смысл данных: нагрузка будет
приписана не той организации, и обнаружится это не скоро.

## 3. Что делает конвейер

Встреченные значения накапливаются. Повторная встреча увеличивает
счётчик, а не создаёт дубликат. После D2 ключ — система-источник, identity_space (набор/роль столбца)
и нормализованное значение: одна и та же строка из двух разных систем может означать
разные организации.

Нормализация схлопывает только регистр и повторяющиеся пробелы. Кавычки,
скобки и номера сохраняются: «Поликлиника №1» и «Поликлиника №11» —
разные организации, и удаление номера их бы объединило.

## 4. Что происходит с несопоставленным фактом

Факт загружается. В витрине остаётся исходное значение организации,
а канонический идентификатор пуст.

Отклонять такие строки нельзя: официального справочника пока нет, и
отклонение оставило бы систему без данных вовсе. Приписывать их
«похожей» организации нельзя тем более.

Аналитика обязана показывать долю несопоставленного отдельно, а не
растворять её в итогах.

## 5. Текущее состояние

По результатам первой полной загрузки:

| Справочник | Значений | Сопоставлено |
|---|---|---|
| Организации | 5 029 | 0 |
| Регионы | 42 | 0 |
| Профили коек | 192 | 0 |

Сорок два региона — это двадцать кодов из очереди, двадцать наименований
из отказов по обращению и два дополнительных наименования по прикреплению.
Сто девяносто два профиля — девяносто пять наименований из направлений
и девяносто семь кодов из очереди, не пересекающихся между собой.

## 6. Что нужно, чтобы закрыть справочник

Ответ владельца данных на три вопроса:

1. Существует ли справочник медицинских организаций с устойчивым кодом?
2. Как соотносятся короткий код и полное юридическое наименование?
3. Существует ли справочник профилей коек, общий для обеих систем?

До ответов сопоставление не выполняется.


## D2: reviewed versioned publication (2026-09-23)

See [ADR-0019](../ADR/0019-versioned-mapping-projection.md). Existing aliases become `LEGACY_UNRESOLVED`, excluded from approved snapshots even if an old canonical ID exists. Role-separated identities such as `IS_BG:REFERRALS:RECEIVING` and `IS_BG:WAITING:DESTINATION` never merge on matching text. Imported ambiguous alias collections remain unresolved; they must be registered in an exact known role before approval.

`app.cli.mapping --actor <subject> register|approve|revoke|publish` is an explicit operator path. Approve requires an existing active canonical target, evidence and exact expected alias version. A conflicting reassignment requires revocation first; REVIEW_REQUIRED is blocked. Approval/revocation, generation advancement and audit commit together. The CLI records reviewed manual decisions; supported stored methods are only OFFICIAL_REFERENCE and MANUAL_APPROVED. Region decisions use the same lifecycle; source-level region projection is used where facts contain that exact source dimension. Profiles remain disabled.

ClickHouse `mapping_projection` stores immutable version, kind, identity_space, source_key, canonical_id. Its organization canonical_id is resolved as hospital_id before aggregation. A candidate is inserted under the PG mapping lock, then count+digest verified; only then may the PG active pointer move. A lost acknowledgement retries missing exact rows and verifies; duplicates/conflicting rows fail closed. The active version is unavailable immediately after any decision, including revocation. A previous cached response cannot restore the old entitlement.

No real dictionary, evidence or approval was created by this implementation. Current owner confirmation is EXTERNAL DEPENDENCY. Historical counts above are historical audit evidence, not current runtime verification.

## Operator review queue

An operator with privileged container/CLI access can run
`python -m app.cli.mapping --actor <operator-subject> review --kind ORGANIZATION --status UNMAPPED --limit 100`
(or `REGION` / `PROFILE`). The command returns a bounded list and total count,
ordered by occurrence count. Each row carries the exact source identity space,
source identifier, occurrence count, status, canonical target if approved,
alias version and the latest approval's actor, timestamp, evidence reference and
mapping version when an approval audit event exists. There is no suggested match
or confidence score without an owner-approved reference. Profiles remain
**review-only** because no canonical profile dimension has been approved.

The CLI is an **operator-only, locally privileged** interface: `--actor` records
the operator-supplied subject but is not OIDC authentication. Do not expose this
command through a web endpoint or delegate its container/database credentials to
ordinary users. Production operation requires an access-controlled operator
environment and independent review of the evidence before `approve`/`publish`.
The list contains organization/region/profile source identifiers only; do not
paste any output into general application logs or public issue trackers.

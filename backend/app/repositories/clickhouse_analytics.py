"""Aggregate-only ClickHouse repository for Situation Center analytics."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Protocol

from app.core.analytics_metrics import observe_clickhouse_query
from app.shared.analytics_contracts import (
    AnalyticsFilter,
    Granularity,
    OrganizationIdentity,
    OrganizationIdentitySpace,
)
from app.shared.analytics_data import (
    QueryScope,
    RawBreakdownCell,
    RawDatasetCoverage,
    RawObservedWaiting,
    RawOrganization,
    RawOverview,
    RawTimeSeriesPoint,
    RawTreatedSnapshot,
    RawWaitingSummary,
)
from app.shared.organization_ref import source_organization_digest


class QueryResult(Protocol):
    result_rows: list[tuple[Any, ...]]


class ClickHouseQueryClient(Protocol):
    def query(
        self, query: str, parameters: dict[str, object] | None = None
    ) -> QueryResult: ...


def _finite_float(value: Any | None) -> float | None:
    """Convert ClickHouse numeric aggregates to JSON-safe finite values."""
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _scope_sql(column: str, scope: QueryScope) -> tuple[str, dict[str, object]]:
    if scope.all_canonical and scope.include_unmapped:
        return "1", {}
    if scope.all_canonical:
        return f"{column} IS NOT NULL", {}

    parameters: dict[str, object] = {
        "hospital_ids": [str(item) for item in scope.canonical_hospital_ids]
    }
    mapped = (
        f"({column} IS NOT NULL AND "
        f"assumeNotNull({column}) IN {{hospital_ids:Array(UUID)}})"
    )
    if scope.include_unmapped:
        return f"({mapped} OR {column} IS NULL)", parameters
    if not scope.canonical_hospital_ids:
        return "0", parameters
    return mapped, parameters


def _base_parameters(filters: AnalyticsFilter) -> dict[str, object]:
    return {
        "date_from": filters.date_from,
        "date_to": filters.date_to,
        "profile": filters.profile or "",
    }


def _profile_sql(filters: AnalyticsFilter, column: str = "profile_source") -> str:
    if filters.profile is None:
        return "1"
    return f"{column} = {{profile:String}}"


def _organization_sql(
    filters: AnalyticsFilter,
    *,
    identity_space: str,
    source_column: str,
    hospital_column: str,
    parameter_prefix: str = "filter",
) -> tuple[str, dict[str, object]]:
    """Build a parameterized identity predicate without joining namespaces."""
    if not filters.organization_ids:
        return "1", {}
    canonical_ids = [
        item.key.removeprefix("canonical:")
        for item in filters.organization_ids
        if item.identity_space is OrganizationIdentitySpace.CANONICAL
    ]
    source_digests = [
        item.key.removeprefix("source:")
        for item in filters.organization_ids
        if item.identity_space is OrganizationIdentitySpace.SOURCE
    ]
    clauses: list[str] = []
    if canonical_ids:
        clauses.append(
            f"({hospital_column} IS NOT NULL AND "
            f"assumeNotNull({hospital_column}) IN "
            f"{{{parameter_prefix}_hospital_ids:Array(UUID)}})"
        )
    if source_digests:
        clauses.append(
            "lower(hex(SHA256(concat("
            f"{{{parameter_prefix}_identity_space:String}}, char(31), "
            f"{source_column})))) IN "
            f"{{{parameter_prefix}_source_digests:Array(String)}}"
        )
    return (
        f"({' OR '.join(clauses)})" if clauses else "0",
        {
            f"{parameter_prefix}_hospital_ids": canonical_ids,
            f"{parameter_prefix}_source_digests": source_digests,
            f"{parameter_prefix}_identity_space": identity_space,
        },
    )


class ClickHouseAnalyticsRepository:
    """Execute bounded aggregate queries; never returns event-level rows."""

    def __init__(self, client: ClickHouseQueryClient) -> None:
        self._client = client

    def _query(
        self, scope: QueryScope, query: str, parameters: dict[str, object] | None = None
    ) -> QueryResult:
        """Replace only our fixed fact sources with a publication/mapping relation.

        No request-supplied SQL identifiers are accepted. Resolving before WHERE
        and GROUP BY gives daily totals and overview exactly the same fact set.
        Canonical IDs baked into legacy facts are not scope entitlements.
        """
        specs = {
            "fact_referral_events": (
                "IS_BG:REFERRALS:RECEIVING",
                "receiving_org_key",
                "receiving_hospital_id",
                "IS_BG:REFERRALS:REGION",
            ),
            "fact_waiting_events": (
                "IS_BG:WAITING:DESTINATION",
                "hospital_source",
                "hospital_id",
                "IS_BG:WAITING:REGION",
            ),
            "fact_refusal_events": (
                "IS_BG:REFUSALS:INCOMING",
                "hospital_source",
                "hospital_id",
                "IS_BG:REFUSALS:REGION",
            ),
            "fact_treated_snapshot": (
                "ERSB:TREATED:ORGANIZATION",
                "hospital_source",
                "hospital_id",
                "ERSB:TREATED:REGION",
            ),
        }
        for table, (space, key, hospital, region_space) in specs.items():
            source = f"FROM {table}"
            if source not in query:
                continue
            has_region = table in {"fact_waiting_events", "fact_refusal_events"}
            excluded = f"{hospital}, region_id" if has_region else hospital
            region_select = ", r.resolved_id AS region_id" if has_region else ""
            region_join = (
                f"""LEFT JOIN (
                    SELECT source_key, toNullable(canonical_id) AS resolved_id
                    FROM mapping_projection
                    WHERE version = {{mapping_version:String}} AND kind = 'REGION'
                      AND identity_space = '{region_space}'
                ) AS r ON f.region_source = r.source_key"""
                if has_region
                else ""
            )
            expected_source = "ЭРСБ" if table == "fact_treated_snapshot" else "ИС БГ"
            relation = f"""FROM (
                SELECT f.* EXCEPT ({excluded}),
                       m.resolved_id AS {hospital}{region_select}
                FROM {table} AS f
                LEFT JOIN (
                    SELECT source_key, toNullable(canonical_id) AS resolved_id
                    FROM mapping_projection
                    WHERE version = {{mapping_version:String}} AND kind = 'ORGANIZATION'
                      AND identity_space = '{space}'
                ) AS m ON f.{key} = m.source_key AND f.source_system = '{expected_source}'
                {region_join}
                WHERE f.import_id IN {{published_import_ids:Array(UUID)}}
            )"""
            query = query.replace(source, relation)
        params = dict(parameters or {})
        params.update(
            mapping_version=scope.mapping_version or "",
            published_import_ids=[str(i) for i in scope.published_import_ids or ()],
        )
        with observe_clickhouse_query("fact_read"):
            return self._client.query(query, parameters=params)

    def _series(
        self,
        *,
        marker: str,
        table: str,
        date_column: str,
        hospital_column: str,
        filters: AnalyticsFilter,
        scope: QueryScope,
        has_profile: bool,
        identity_space: str,
        source_column: str,
    ) -> tuple[RawTimeSeriesPoint, ...]:
        scope_sql, scope_params = _scope_sql(hospital_column, scope)
        identity_sql, identity_params = _organization_sql(
            filters,
            identity_space=identity_space,
            source_column=source_column,
            hospital_column=hospital_column,
        )
        bucket = (
            f"toStartOfDay({date_column})"
            if filters.granularity is Granularity.DAY
            else f"toStartOfWeek({date_column}, 1)"
        )
        profile_sql = _profile_sql(filters) if has_profile else "1"
        # Identifiers above are selected only from internal allowlists; all
        # request values remain ClickHouse parameters.
        query = f"""
            /* {marker} */
            SELECT {bucket} AS period_start, count() AS value
            FROM {table}
            WHERE {date_column} >= {{date_from:DateTime64(3)}}
              AND {date_column} <= {{date_to:DateTime64(3)}}
              AND {scope_sql}
              AND {identity_sql}
              AND {profile_sql}
            GROUP BY period_start
            ORDER BY period_start
            LIMIT 400
        """
        parameters = _base_parameters(filters) | scope_params | identity_params
        rows = self._query(scope, query, parameters=parameters).result_rows
        return tuple(RawTimeSeriesPoint(row[0], int(row[1])) for row in rows)

    def referral_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]:
        return self._series(
            marker="analytics:referral-timeseries",
            table="fact_referral_events",
            date_column="registration_dt",
            hospital_column="receiving_hospital_id",
            filters=filters,
            scope=scope,
            has_profile=True,
            identity_space="IS_BG:REFERRALS:RECEIVING",
            source_column="receiving_org_key",
        )

    def refusal_timeseries(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> tuple[RawTimeSeriesPoint, ...]:
        return self._series(
            marker="analytics:refusal-timeseries",
            table="fact_refusal_events",
            date_column="refuse_dt",
            hospital_column="hospital_id",
            filters=filters,
            scope=scope,
            has_profile=False,
            identity_space="IS_BG:REFUSALS:INCOMING",
            source_column="hospital_source",
        )

    def waiting_summary(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> RawWaitingSummary:
        scope_sql, scope_params = _scope_sql("hospital_id", scope)
        identity_sql, identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:WAITING:DESTINATION",
            source_column="hospital_source",
            hospital_column="hospital_id",
        )
        age = (
            "(toUnixTimestamp64Milli(snapshot_dt) - "
            "toUnixTimestamp64Milli(registration_dt)) / 86400000.0"
        )
        profile_sql = _profile_sql(filters)
        query = f"""
            /* analytics:waiting-summary */
            WITH (
                SELECT max(snapshot_dt)
                FROM fact_waiting_events
                WHERE registration_dt >= {{date_from:DateTime64(3)}}
                  AND registration_dt <= {{date_to:DateTime64(3)}}
                  AND {scope_sql}
                  AND {identity_sql}
                  AND {profile_sql}
            ) AS latest_snapshot
            SELECT
                latest_snapshot,
                count(),
                countIf(snapshot_dt < registration_dt),
                quantileTDigestIf(0.5)({age}, snapshot_dt >= registration_dt),
                quantileTDigestIf(0.75)({age}, snapshot_dt >= registration_dt),
                quantileTDigestIf(0.9)({age}, snapshot_dt >= registration_dt),
                maxIf({age}, snapshot_dt >= registration_dt)
            FROM fact_waiting_events
            WHERE snapshot_dt = latest_snapshot
              AND registration_dt >= {{date_from:DateTime64(3)}}
              AND registration_dt <= {{date_to:DateTime64(3)}}
              AND {scope_sql}
              AND {identity_sql}
              AND {profile_sql}
        """
        rows = self._query(
            scope,
            query,
            parameters=_base_parameters(filters) | scope_params | identity_params,
        ).result_rows
        if not rows:
            return RawWaitingSummary(None, 0, 0, None, None, None, None)
        row = rows[0]
        waiting_records = int(row[1])
        if waiting_records == 0:
            return RawWaitingSummary(None, 0, int(row[2]), None, None, None, None)
        return RawWaitingSummary(
            snapshot_dt=row[0],
            waiting_records=waiting_records,
            excluded_chronology_conflicts=int(row[2]),
            median_days=_finite_float(row[3]),
            p75_days=_finite_float(row[4]),
            p90_days=_finite_float(row[5]),
            oldest_days=_finite_float(row[6]),
        )

    def observed_waiting(
        self, filters: AnalyticsFilter, scope: QueryScope
    ) -> RawObservedWaiting:
        scope_sql, scope_params = _scope_sql("receiving_hospital_id", scope)
        identity_sql, identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFERRALS:RECEIVING",
            source_column="receiving_org_key",
            hospital_column="receiving_hospital_id",
        )
        duration = (
            "(toUnixTimestamp64Milli(hospitalization_dt) - "
            "toUnixTimestamp64Milli(registration_dt)) / 86400000.0"
        )
        valid = "hospitalization_dt IS NOT NULL AND hospitalization_dt >= registration_dt"
        profile_sql = _profile_sql(filters)
        query = f"""
            /* analytics:observed-waiting */
            SELECT
                countIf({valid}),
                countIf(
                    hospitalization_dt IS NOT NULL
                    AND hospitalization_dt < registration_dt
                ),
                avgIf({duration}, {valid}),
                quantileTDigestIf(0.5)({duration}, {valid}),
                quantileTDigestIf(0.75)({duration}, {valid}),
                quantileTDigestIf(0.9)({duration}, {valid})
            FROM fact_referral_events
            WHERE registration_dt >= {{date_from:DateTime64(3)}}
              AND registration_dt <= {{date_to:DateTime64(3)}}
              AND {scope_sql}
              AND {identity_sql}
              AND {profile_sql}
        """
        rows = self._query(
            scope,
            query,
            parameters=_base_parameters(filters) | scope_params | identity_params,
        ).result_rows
        if not rows:
            return RawObservedWaiting(0, 0, None, None, None, None)
        row = rows[0]
        observed_records = int(row[0])
        if observed_records == 0:
            return RawObservedWaiting(0, int(row[1]), None, None, None, None)
        return RawObservedWaiting(
            observed_records=observed_records,
            excluded_chronology_conflicts=int(row[1]),
            mean_days=_finite_float(row[2]),
            median_days=_finite_float(row[3]),
            p75_days=_finite_float(row[4]),
            p90_days=_finite_float(row[5]),
        )

    def overview(self, filters: AnalyticsFilter, scope: QueryScope) -> RawOverview:
        referral_scope, referral_params = _scope_sql("receiving_hospital_id", scope)
        waiting_scope, waiting_params = _scope_sql("hospital_id", scope)
        refusal_scope, refusal_params = _scope_sql("hospital_id", scope)
        referral_identity, referral_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFERRALS:RECEIVING",
            source_column="receiving_org_key",
            hospital_column="receiving_hospital_id",
        )
        waiting_identity, waiting_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:WAITING:DESTINATION",
            source_column="hospital_source",
            hospital_column="hospital_id",
        )
        refusal_identity, refusal_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFUSALS:INCOMING",
            source_column="hospital_source",
            hospital_column="hospital_id",
        )
        common = _base_parameters(filters)

        referral_query = f"""
            /* analytics:overview-referrals */
            SELECT count(),
                   countIf(refusal_dt IS NULL AND hospitalization_dt IS NOT NULL
                           AND hospitalization_dt >= registration_dt),
                   countIf(
                       (hospitalization_dt IS NOT NULL
                        AND hospitalization_dt < registration_dt)
                       OR (refusal_dt IS NOT NULL
                           AND refusal_dt < registration_dt)
                   ),
                   uniqExact(receiving_org_key)
            FROM fact_referral_events
            WHERE registration_dt >= {{date_from:DateTime64(3)}}
              AND registration_dt <= {{date_to:DateTime64(3)}}
              AND {referral_scope}
              AND {referral_identity}
              AND {_profile_sql(filters)}
        """
        waiting_query = f"""
            /* analytics:overview-waiting */
            SELECT count(), uniqExact(hospital_source), uniqExact(region_source)
            FROM fact_waiting_events
            WHERE registration_dt >= {{date_from:DateTime64(3)}}
              AND registration_dt <= {{date_to:DateTime64(3)}}
              AND {waiting_scope}
              AND {waiting_identity}
              AND {_profile_sql(filters)}
        """
        refusal_query = f"""
            /* analytics:overview-refusals */
            SELECT count(), uniqExact(hospital_source), uniqExact(region_source)
            FROM fact_refusal_events
            WHERE refuse_dt >= {{date_from:DateTime64(3)}}
              AND refuse_dt <= {{date_to:DateTime64(3)}}
              AND {refusal_scope}
              AND {refusal_identity}
        """
        ref = self._query(
            scope,
            referral_query,
            parameters=common | referral_params | referral_identity_params,
        ).result_rows[0]
        waiting = self._query(
            scope,
            waiting_query,
            parameters=common | waiting_params | waiting_identity_params,
        ).result_rows[0]
        refusal = self._query(
            scope,
            refusal_query,
            parameters=common | refusal_params | refusal_identity_params,
        ).result_rows[0]
        return RawOverview(
            referrals_total=int(ref[0]),
            waiting_records=int(waiting[0]),
            refusals_total=int(refusal[0]),
            hospitalized_total=int(ref[1]),
            unknown_records=int(ref[2]),
            represented_organizations=int(ref[3]) + int(waiting[1]) + int(refusal[1]),
            represented_regions=int(waiting[2]) + int(refusal[2]),
        )

    def organizations(
        self,
        filters: AnalyticsFilter,
        scope: QueryScope,
        *,
        limit: int,
        offset: int,
    ) -> tuple[tuple[RawOrganization, ...], int]:
        referral_scope, referral_params = _scope_sql("m.resolved_id", scope)
        waiting_scope, waiting_params = _scope_sql("m.resolved_id", scope)
        refusal_scope, refusal_params = _scope_sql("m.resolved_id", scope)
        referral_identity, referral_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFERRALS:RECEIVING",
            source_column="receiving_org_key",
            hospital_column="m.resolved_id",
            parameter_prefix="referral_filter",
        )
        waiting_identity, waiting_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:WAITING:DESTINATION",
            source_column="hospital_source",
            hospital_column="m.resolved_id",
            parameter_prefix="waiting_filter",
        )
        refusal_identity, refusal_identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFUSALS:INCOMING",
            source_column="hospital_source",
            hospital_column="m.resolved_id",
            parameter_prefix="refusal_filter",
        )
        duration = (
            "(toUnixTimestamp64Milli(hospitalization_dt) - "
            "toUnixTimestamp64Milli(registration_dt)) / 86400000.0"
        )
        query = f"""
            /* analytics:organizations */
            SELECT identity_space, source_system, source_value,
                   canonical_hospital_id, referrals_total, waiting_records,
                   refusals_total, observed_waiting_median_days, count() OVER() AS total
            FROM (
                SELECT
                    'IS_BG:REFERRALS:RECEIVING' AS identity_space,
                    source_system,
                    receiving_org_key AS source_value,
                    m.resolved_id AS canonical_hospital_id,
                    referrals_total,
                    toUInt64(0) AS waiting_records,
                    toUInt64(0) AS refusals_total,
                    observed_waiting_median_days
                FROM (
                    SELECT f.source_system, f.receiving_org_key,
                           count() AS referrals_total,
                           quantileTDigestIf(0.5)({duration},
                               f.hospitalization_dt IS NOT NULL
                               AND f.hospitalization_dt >= f.registration_dt)
                               AS observed_waiting_median_days
                    FROM fact_referral_events AS f
                    WHERE f.import_id IN {{published_import_ids:Array(UUID)}}
                      AND f.registration_dt >= {{date_from:DateTime64(3)}}
                      AND f.registration_dt <= {{date_to:DateTime64(3)}}
                      AND {_profile_sql(filters, 'f.profile_source')}
                    GROUP BY source_system, receiving_org_key
                ) AS grouped
                LEFT JOIN (
                    SELECT source_key, toNullable(canonical_id) AS resolved_id
                    FROM mapping_projection
                    WHERE version = {{mapping_version:String}}
                      AND kind = 'ORGANIZATION'
                      AND identity_space = 'IS_BG:REFERRALS:RECEIVING'
                ) AS m ON grouped.receiving_org_key = m.source_key
                    AND grouped.source_system = 'ИС БГ'
                WHERE {referral_scope} AND {referral_identity}
                UNION ALL
                SELECT
                    'IS_BG:WAITING:DESTINATION', source_system, hospital_source,
                    m.resolved_id, toUInt64(0), waiting_records, toUInt64(0), NULL
                FROM (
                    SELECT f.source_system, f.hospital_source,
                           count() AS waiting_records
                    FROM fact_waiting_events AS f
                    WHERE f.import_id IN {{published_import_ids:Array(UUID)}}
                      AND f.registration_dt >= {{date_from:DateTime64(3)}}
                      AND f.registration_dt <= {{date_to:DateTime64(3)}}
                      AND {_profile_sql(filters, 'f.profile_source')}
                    GROUP BY source_system, hospital_source
                ) AS grouped
                LEFT JOIN (
                    SELECT source_key, toNullable(canonical_id) AS resolved_id
                    FROM mapping_projection
                    WHERE version = {{mapping_version:String}}
                      AND kind = 'ORGANIZATION'
                      AND identity_space = 'IS_BG:WAITING:DESTINATION'
                ) AS m ON grouped.hospital_source = m.source_key
                    AND grouped.source_system = 'ИС БГ'
                WHERE {waiting_scope} AND {waiting_identity}
                UNION ALL
                SELECT
                    'IS_BG:REFUSALS:INCOMING', source_system, hospital_source,
                    m.resolved_id, toUInt64(0), toUInt64(0), refusals_total, NULL
                FROM (
                    SELECT f.source_system, f.hospital_source,
                           count() AS refusals_total
                    FROM fact_refusal_events AS f
                    WHERE f.import_id IN {{published_import_ids:Array(UUID)}}
                      AND f.refuse_dt >= {{date_from:DateTime64(3)}}
                      AND f.refuse_dt <= {{date_to:DateTime64(3)}}
                    GROUP BY source_system, hospital_source
                ) AS grouped
                LEFT JOIN (
                    SELECT source_key, toNullable(canonical_id) AS resolved_id
                    FROM mapping_projection
                    WHERE version = {{mapping_version:String}}
                      AND kind = 'ORGANIZATION'
                      AND identity_space = 'IS_BG:REFUSALS:INCOMING'
                ) AS m ON grouped.hospital_source = m.source_key
                    AND grouped.source_system = 'ИС БГ'
                WHERE {refusal_scope} AND {refusal_identity}
            )
            ORDER BY referrals_total + waiting_records + refusals_total DESC,
                     identity_space, source_value
            LIMIT {{limit:UInt64}} OFFSET {{offset:UInt64}}
        """
        parameters = (
            _base_parameters(filters)
            | referral_params
            | waiting_params
            | refusal_params
            | referral_identity_params
            | waiting_identity_params
            | refusal_identity_params
            | {
                "limit": limit,
                "offset": offset,
                "mapping_version": scope.mapping_version or "",
                "published_import_ids": [
                    str(item) for item in scope.published_import_ids or ()
                ],
            }
        )
        # Publication filtering precedes aggregation; mapping follows it. The
        # generic fact rewrite joins every source row and is slower for lists.
        with observe_clickhouse_query("organizations"):
            rows = self._client.query(query, parameters=parameters).result_rows
        total = int(rows[0][8]) if rows else 0
        organizations = tuple(
            RawOrganization(
                identity_space=str(row[0]),
                source_system=str(row[1]),
                source_value=str(row[2]),
                canonical_hospital_id=row[3],
                referrals_total=int(row[4]),
                waiting_records=int(row[5]),
                refusals_total=int(row[6]),
                observed_waiting_median_days=_finite_float(row[7]),
            )
            for row in rows
        )
        return organizations, total

    def _treated_snapshot(
        self, hospital_id: object | None, scope: QueryScope
    ) -> RawTreatedSnapshot | None:
        if hospital_id is None:
            return None
        query = """
            /* analytics:treated-snapshot */
            SELECT snapshot_load_dt, discharged_total, discharged_children,
                   treated_budget, treated_paid, discharged_within_day,
                   deaths_total, bed_days, toFloat64(amount_to_pay)
            FROM fact_treated_snapshot
            WHERE hospital_id = {hospital_id:UUID}
            ORDER BY snapshot_load_dt DESC
            LIMIT 1
        """
        rows = self._query(
            scope, query, parameters={"hospital_id": str(hospital_id)}
        ).result_rows
        if not rows:
            return None
        row = rows[0]
        return RawTreatedSnapshot(
            snapshot_load_dt=row[0],
            discharged_total=int(row[1]),
            discharged_children=int(row[2]),
            treated_budget=int(row[3]),
            treated_paid=int(row[4]),
            discharged_within_day=int(row[5]),
            deaths_total=int(row[6]),
            bed_days=int(row[7]),
            amount_to_pay=float(row[8]),
        )

    def organization_detail(
        self,
        identity_key: str,
        filters: AnalyticsFilter,
        scope: QueryScope,
    ) -> tuple[RawOrganization, RawTreatedSnapshot | None] | None:
        if identity_key.startswith("canonical:"):
            hospital_id = identity_key.removeprefix("canonical:")
            narrowed = replace(
                scope,
                canonical_hospital_ids=tuple(
                    item
                    for item in scope.canonical_hospital_ids
                    if str(item) == hospital_id
                ),
                all_canonical=False,
                include_unmapped=False,
            )
            if scope.all_canonical:
                import uuid

                narrowed = replace(
                    scope,
                    canonical_hospital_ids=(uuid.UUID(hospital_id),),
                    all_canonical=False,
                    include_unmapped=False,
                )
            overview = self.overview(filters, narrowed)
            raw = RawOrganization(
                identity_space="CANONICAL",
                source_system="MULTIPLE",
                source_value="",
                canonical_hospital_id=narrowed.canonical_hospital_ids[0]
                if narrowed.canonical_hospital_ids
                else None,
                referrals_total=overview.referrals_total,
                waiting_records=overview.waiting_records,
                refusals_total=overview.refusals_total,
                observed_waiting_median_days=self.observed_waiting(
                    filters, narrowed
                ).median_days,
            )
            if raw.canonical_hospital_id is None:
                return None
            return raw, self._treated_snapshot(raw.canonical_hospital_id, narrowed)

        digest = identity_key.removeprefix("source:")
        narrowed_filters = replace(
            filters, organization_ids=(OrganizationIdentity.source(digest),)
        )
        candidates, _ = self.organizations(narrowed_filters, scope, limit=1, offset=0)
        if not candidates:
            return None
        item = candidates[0]
        if source_organization_digest(item.identity_space, item.source_value) != digest:
            return None
        return item, self._treated_snapshot(item.canonical_hospital_id, scope)

    def dataset_coverage(self, scope: QueryScope) -> tuple[RawDatasetCoverage, ...]:
        specs = (
            (
                "REFERRALS",
                "fact_referral_events",
                "registration_dt",
                None,
                "receiving_hospital_id",
            ),
            (
                "WAITING",
                "fact_waiting_events",
                "registration_dt",
                "snapshot_dt",
                "hospital_id",
            ),
            ("REFUSALS", "fact_refusal_events", "refuse_dt", None, "hospital_id"),
            (
                "TREATED",
                "fact_treated_snapshot",
                "snapshot_load_dt",
                "snapshot_load_dt",
                "hospital_id",
            ),
        )
        results: list[RawDatasetCoverage] = []
        for dataset, table, event_column, load_column, hospital_column in specs:
            scope_sql, parameters = _scope_sql(hospital_column, scope)
            load_expr = f"max({load_column})" if load_column else "NULL"
            query = f"""
                /* analytics:coverage:{dataset} */
                SELECT min({event_column}), max({event_column}), {load_expr}
                FROM {table}
                WHERE {scope_sql}
            """
            rows = self._query(scope, query, parameters=parameters).result_rows
            row = rows[0] if rows else (None, None, None)
            results.append(RawDatasetCoverage(dataset, row[0], row[1], row[2]))
        return tuple(results)

    def refusal_breakdown(
        self,
        filters: AnalyticsFilter,
        scope: QueryScope,
        *,
        dimension: str,
    ) -> tuple[RawBreakdownCell, ...]:
        allowed = {
            "finance_source": "finance_source",
            "icd_group": "substring(icd10_code, 1, 3)",
            "resident": "resident",
            "insured": "insured",
            "benefit_category": "benefit_category",
        }
        column = allowed[dimension]
        scope_sql, scope_params = _scope_sql("hospital_id", scope)
        identity_sql, identity_params = _organization_sql(
            filters,
            identity_space="IS_BG:REFUSALS:INCOMING",
            source_column="hospital_source",
            hospital_column="hospital_id",
        )
        query = f"""
            /* analytics:refusal-breakdown */
            SELECT {column} AS label, count() AS value
            FROM fact_refusal_events
            WHERE refuse_dt >= {{date_from:DateTime64(3)}}
              AND refuse_dt <= {{date_to:DateTime64(3)}}
              AND {scope_sql}
              AND {identity_sql}
            GROUP BY label
            ORDER BY value DESC
            LIMIT 100
        """
        rows = self._query(
            scope,
            query,
            parameters=_base_parameters(filters) | scope_params | identity_params,
        ).result_rows
        return tuple(
            RawBreakdownCell(str(row[0] or "UNKNOWN"), int(row[1])) for row in rows
        )

"""Bounded aggregate inputs for Signal Engine evaluation.

The adapter combines ClickHouse aggregates with PostgreSQL lineage metadata.
It never returns event rows and never performs dynamic SQL from caller input.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.analytics import Forecast
from app.models.data_import import DataImport
from app.models.delivery import Delivery
from app.models.enums import DataImportStatus, ForecastStatus
from app.models.forecast_point import ForecastPoint
from app.models.model_version import ModelVersion
from app.models.quality import DataQualityResult
from app.repositories.delivery import SqlAlchemyDeliveryRepository
from app.shared.signal_engine import (
    DailyAggregate,
    ForecastEvidence,
    FreshnessEvidence,
    QualityMeasurement,
    TimeSeriesEvidence,
)


class QueryResult(Protocol):
    result_rows: list[tuple[Any, ...]]


class ClickHouseQueryClient(Protocol):
    def query(
        self, query: str, *, parameters: dict[str, object] | None = None
    ) -> QueryResult: ...


@dataclass(frozen=True, slots=True)
class _DatasetSpec:
    table: str
    event_column: str
    source: str
    supports_daily: bool


_DATASETS: dict[str, _DatasetSpec] = {
    "REFERRALS": _DatasetSpec("fact_referral_events", "registration_dt", "ИС БГ", True),
    "WAITING": _DatasetSpec("fact_waiting_events", "snapshot_dt", "ИС БГ", False),
    "REFUSALS": _DatasetSpec("fact_refusal_events", "refuse_dt", "ИС БГ", True),
    "TREATED": _DatasetSpec("fact_treated_snapshot", "snapshot_load_dt", "ЭРСБ", False),
}

_BASELINE_MODELS = frozenset({"naive_last", "weekly_naive", "moving_average_7"})


class SqlClickHouseSignalInputRepository:
    def __init__(
        self,
        client: ClickHouseQueryClient,
        session_factory: sessionmaker[Session] | None,
    ) -> None:
        self._client = client
        self._session_factory = session_factory

    @staticmethod
    def _spec(dataset_type: str) -> _DatasetSpec:
        try:
            return _DATASETS[dataset_type]
        except KeyError as exc:
            raise ValueError(f"Dataset {dataset_type!r} не поддерживается") from exc

    def latest_event_at(self, dataset_type: str) -> datetime | None:
        spec = self._spec(dataset_type)
        # Identifiers are selected from the closed _DATASETS map; user input is
        # never interpolated. Values remain ClickHouse parameters.
        import_ids = tuple(
            row.id
            for row in self._completed_imports()
            if row.dataset_type == dataset_type and row.source == spec.source
        )
        if not import_ids:
            return None
        query = f"""
            /* signal-engine:latest:{dataset_type} */
            SELECT max({spec.event_column})
            FROM {spec.table}
            WHERE import_id IN {{published_import_ids:Array(UUID)}}
            """
        rows = self._client.query(
            query, parameters={"published_import_ids": [str(i) for i in import_ids]}
        ).result_rows
        if not rows or rows[0][0] is None:
            return None
        value = rows[0][0]
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, date):
            return datetime.combine(value, datetime.max.time(), tzinfo=UTC)
        raise TypeError(f"Неожиданный тип временной метки: {type(value).__name__}")

    def daily_evidence(
        self,
        dataset_type: str,
        *,
        before: date,
        source_is_current: bool,
        limit_days: int,
    ) -> TimeSeriesEvidence:
        spec = self._spec(dataset_type)
        if not spec.supports_daily:
            raise ValueError(f"Dataset {dataset_type!r} не имеет event daily series")
        empty = TimeSeriesEvidence(
            dataset_type,
            spec.source,
            (),
            {"schema_version": "published-signal-input-v1", "completeness": "UNKNOWN"},
            False,
        )
        if self._session_factory is None:
            return empty
        with self._session_factory() as session, session.begin():
            deliveries = SqlAlchemyDeliveryRepository(session)
            deliveries.lock_source(spec.source, dataset_type)
            ready = deliveries.readiness(dataset_type, source_system=spec.source)
            if (
                ready.completeness != "COMPLETE"
                or not ready.published_import_ids
                or ready.confirmed_complete_through is None
                or ready.confirmed_complete_through < before - timedelta(days=1)
            ):
                return empty
            query = f"""
                /* signal-engine:daily:{dataset_type} */
                SELECT event_date, value FROM (
                    SELECT toDate({spec.event_column}) AS event_date, count() AS value
                    FROM {spec.table}
                    WHERE toDate({spec.event_column}) < {{before:Date}}
                      AND toDate({spec.event_column}) >= {{after:Date}}
                      AND import_id IN {{published_import_ids:Array(UUID)}}
                    GROUP BY event_date ORDER BY event_date DESC
                    LIMIT {{limit_days:UInt64}}
                ) ORDER BY event_date
            """
            rows = self._client.query(
                query,
                parameters={
                    "before": before,
                    "after": before - timedelta(days=limit_days),
                    "limit_days": limit_days,
                    "published_import_ids": [str(i) for i in ready.published_import_ids],
                },
            ).result_rows
            return TimeSeriesEvidence(
                dataset_type,
                spec.source,
                tuple(
                    DailyAggregate(row[0], int(row[1]), is_complete=True) for row in rows
                ),
                {
                    "schema_version": "published-signal-input-v1",
                    "import_ids": [str(i) for i in ready.published_import_ids],
                    "delivery_watermark": ready.publication_watermark,
                    "confirmed_complete_through": (
                        ready.confirmed_complete_through.isoformat()
                    ),
                },
                source_is_current,
            )

    def _completed_imports(self) -> list[DataImport]:
        if self._session_factory is None:
            return []
        with self._session_factory() as session:
            rows = session.scalars(
                select(DataImport)
                .outerjoin(Delivery, DataImport.delivery_id == Delivery.id)
                .where(
                    DataImport.status == DataImportStatus.COMPLETED,
                    or_(DataImport.delivery_id.is_(None), Delivery.status == "PUBLISHED"),
                )
                .order_by(DataImport.dataset_type, DataImport.completed_at, DataImport.id)
            ).all()
            session.expunge_all()
        return list(rows)

    @staticmethod
    def _watermark(rows: list[DataImport]) -> dict[str, object]:
        completed = [row.completed_at for row in rows if row.completed_at is not None]
        return {
            "completed_at": max(completed).isoformat() if completed else None,
            "import_ids": [str(row.id) for row in rows],
            "file_hashes": [row.file_hash for row in rows],
        }

    def _watermark_for(self, dataset_type: str) -> dict[str, object]:
        return self._watermark(
            [row for row in self._completed_imports() if row.dataset_type == dataset_type]
        )

    def freshness_evidence(self) -> tuple[FreshnessEvidence, ...]:
        imports = self._completed_imports()
        grouped: dict[str, list[DataImport]] = defaultdict(list)
        for row in imports:
            grouped[row.dataset_type].append(row)
        return tuple(
            FreshnessEvidence(
                dataset_type=dataset_type,
                source=spec.source,
                latest_successful_at=self.latest_event_at(dataset_type),
                watermark=self._watermark(grouped.get(dataset_type, [])),
            )
            for dataset_type, spec in _DATASETS.items()
        )

    def quality_measurements(self) -> tuple[QualityMeasurement, ...]:
        if self._session_factory is None:
            return ()
        imports = self._completed_imports()
        if not imports:
            return ()
        import_by_id = {row.id: row for row in imports}
        with self._session_factory() as session:
            findings = session.scalars(
                select(DataQualityResult).where(
                    DataQualityResult.data_import_id.in_(tuple(import_by_id))
                )
            ).all()

        grouped_imports: dict[str, list[DataImport]] = defaultdict(list)
        for row in imports:
            grouped_imports[row.dataset_type].append(row)
        measurements: list[QualityMeasurement] = []
        for dataset_type, rows in sorted(grouped_imports.items()):
            source = self._spec(dataset_type).source
            watermark = self._watermark(rows)
            measurements.append(
                QualityMeasurement(
                    dataset_type=dataset_type,
                    source=source,
                    rule_code="REJECTED_ROWS",
                    affected_rows=sum(row.rows_rejected for row in rows),
                    eligible_rows=sum(row.rows_read for row in rows),
                    denominator_code="ROWS_READ",
                    watermark=watermark,
                )
            )

        affected: dict[tuple[str, str], int] = defaultdict(int)
        for finding in findings:
            if finding.rule_code == "CONDITIONAL_NULL_EXPECTED":
                continue
            dataset = import_by_id[finding.data_import_id].dataset_type
            affected[(dataset, finding.rule_code)] += finding.affected_rows
        for (dataset_type, rule_code), count in sorted(affected.items()):
            rows = grouped_imports[dataset_type]
            measurements.append(
                QualityMeasurement(
                    dataset_type=dataset_type,
                    source=self._spec(dataset_type).source,
                    rule_code=rule_code,
                    affected_rows=count,
                    # Existing DataQualityResult stores the numerator only.
                    # rows_read is not a truthful denominator for chronology or
                    # mapping rules, so no Signal may be created from it.
                    eligible_rows=None,
                    denominator_code=None,
                    watermark=self._watermark(rows),
                )
            )
        return tuple(measurements)

    def latest_forecast(self, *, now: datetime) -> ForecastEvidence | None:
        if self._session_factory is None:
            return None
        with self._session_factory() as session:
            forecast = session.scalars(
                select(Forecast)
                .where(
                    Forecast.scope_type == "GLOBAL",
                    Forecast.target == "DAILY_REFERRAL_COUNT",
                    Forecast.status == ForecastStatus.VALID,
                )
                .order_by(Forecast.generated_at.desc(), Forecast.id.desc())
                .limit(1)
            ).first()
            if (
                forecast is None
                or forecast.forecast_start is None
                or forecast.forecast_end is None
            ):
                return None
            points = session.scalars(
                select(ForecastPoint)
                .where(ForecastPoint.forecast_id == forecast.id)
                .order_by(ForecastPoint.forecast_date)
            ).all()
            model = (
                session.get(ModelVersion, forecast.model_version_id)
                if forecast.model_version_id is not None
                else None
            )
            result = ForecastEvidence(
                forecast_id=forecast.id,
                source="ИС БГ",
                freshness_status=(
                    "CURRENT" if forecast.forecast_end >= now.date() else "STALE"
                ),
                status=ForecastStatus(forecast.status).value,
                horizon_start=forecast.forecast_start,
                horizon_end=forecast.forecast_end,
                forecast_value=sum(float(point.predicted_value) for point in points),
                baseline_value=sum(float(point.baseline_value) for point in points),
                selected_model=forecast.selected_model,
                selected_model_type=(
                    "BASELINE" if forecast.selected_model in _BASELINE_MODELS else "ML"
                ),
                model_version=forecast.model_version,
                generated_at=forecast.generated_at,
                watermark=dict(forecast.dataset_watermark),
            )
            # Keep a read detached from the session. `model` is read only to
            # ensure the FK resolves; no algorithm name is exposed as a claim.
            _ = model
        return result

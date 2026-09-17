from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.business.signals.contracts import (
    DailyAggregate,
    EvaluationStatus,
    ForecastEvidence,
    FreshnessEvidence,
    PersistenceStatus,
    QualityMeasurement,
    TimeSeriesEvidence,
)
from app.business.signals.evaluation import SignalEvaluationService
from app.business.signals.policy import SignalPolicy
from app.models.enums import AuditAction
from tests.fakes import (
    FakeSignalRepository,
    FakeStore,
    FakeUnitOfWork,
    unit_of_work_factory,
)

NOW = datetime(2025, 4, 1, 12, tzinfo=UTC)


class Inputs:
    def __init__(self, *, watermark: str = "import-1") -> None:
        self.watermark = watermark
        self.daily_calls: list[tuple[str, bool]] = []

    def _watermark(self):
        return {"import_ids": [self.watermark]}

    def freshness_evidence(self):
        return (
            FreshnessEvidence(
                "REFERRALS",
                "ИС БГ",
                NOW - timedelta(hours=100),
                self._watermark(),
            ),
            FreshnessEvidence(
                "REFUSALS",
                "ИС БГ",
                NOW - timedelta(hours=1),
                self._watermark(),
            ),
        )

    def quality_measurements(self):
        return (
            QualityMeasurement(
                "REFERRALS",
                "ИС БГ",
                "HOSPITALIZATION_BEFORE_REGISTRATION",
                104_644,
                None,
                None,
                self._watermark(),
            ),
        )

    def daily_evidence(
        self,
        dataset_type,
        *,
        before,
        source_is_current,
        limit_days,
    ):
        del before
        self.daily_calls.append((dataset_type, source_is_current))
        start = date(2025, 1, 1)
        return TimeSeriesEvidence(
            dataset_type=dataset_type,
            source="ИС БГ",
            points=tuple(
                DailyAggregate(
                    start + timedelta(days=index),
                    100 if index >= limit_days - 7 else 50,
                )
                for index in range(limit_days)
            ),
            watermark=self._watermark(),
            source_is_current=source_is_current,
        )

    def latest_forecast(self, *, now):
        return ForecastEvidence(
            forecast_id=uuid.uuid4(),
            source="ИС БГ",
            freshness_status="STALE",
            status="VALID",
            horizon_start=now.date(),
            horizon_end=now.date() + timedelta(days=6),
            forecast_value=2_000,
            baseline_value=1_000,
            selected_model="weekly_naive",
            selected_model_type="BASELINE",
            model_version="v1",
            generated_at=now - timedelta(days=100),
            watermark=self._watermark(),
        )


def _service(store: FakeStore, inputs: Inputs) -> SignalEvaluationService:
    return SignalEvaluationService(
        uow_factory=unit_of_work_factory(store),
        inputs=inputs,
        policy=SignalPolicy(),
        clock=lambda: NOW,
    )


def test_evaluation_reports_suppressed_and_insufficient_without_fake_signals(
    store: FakeStore,
) -> None:
    inputs = Inputs()

    report = _service(store, inputs).evaluate_all()

    by_name = {(item.evaluator, item.dataset_type): item for item in report.records}
    assert by_name[("DATA_STALE", "REFERRALS")].status is EvaluationStatus.FIRED
    assert by_name[("REFERRAL_SPIKE", "REFERRALS")].status is EvaluationStatus.SUPPRESSED
    assert by_name[("REFUSAL_SPIKE", "REFUSALS")].status is EvaluationStatus.FIRED
    assert by_name[("DATA_QUALITY_DEGRADED", "REFERRALS")].status is (
        EvaluationStatus.INSUFFICIENT_DATA
    )
    assert by_name[("FORECAST_INFLOW_GROWTH", None)].status is (
        EvaluationStatus.SUPPRESSED
    )
    assert by_name[("FORECAST_INFLOW_GROWTH", None)].reason == "FORECAST_STALE"
    quality_record = by_name[("DATA_QUALITY_DEGRADED", "REFERRALS")]
    assert quality_record.metadata["rule_code"] == ("HOSPITALIZATION_BEFORE_REGISTRATION")
    assert quality_record.metadata["affected_rows"] == 104_644
    serialized_quality = next(
        item
        for item in report.as_dict()["records"]
        if item["evaluator"] == "DATA_QUALITY_DEGRADED"
    )
    assert serialized_quality["metadata"] == quality_record.metadata
    assert len(store.signals) == 2


def test_same_evaluation_is_idempotent_and_audited_once(store: FakeStore) -> None:
    service = _service(store, Inputs())

    first = service.evaluate_all()
    second = service.evaluate_all()

    assert len(store.signals) == 2
    assert sum(event.action == AuditAction.SIGNAL_CREATED for event in store.audit) == 2
    assert any(
        record.persistence is PersistenceStatus.SKIP_IDEMPOTENT
        for record in second.records
    )
    assert all(
        record.persistence is PersistenceStatus.CREATED
        for record in first.records
        if record.status is EvaluationStatus.FIRED
    )


def test_concurrent_exact_replay_is_reported_as_idempotent(store: FakeStore) -> None:
    """A competing insert after the pre-check must not fail the evaluation."""
    _service(store, Inputs()).evaluate_all()
    audit_count = len(store.audit)

    class ConcurrentReplayRepository(FakeSignalRepository):
        def find_by_dedup_key(self, dedup_key: str):
            # Simulate the race: the pre-check ran before the competing commit.
            del dedup_key
            return None

    class ConcurrentReplayUnitOfWork(FakeUnitOfWork):
        def __init__(self, fake_store: FakeStore) -> None:
            super().__init__(fake_store)
            self.signals = ConcurrentReplayRepository(fake_store)

    service = SignalEvaluationService(
        uow_factory=lambda: ConcurrentReplayUnitOfWork(store),
        inputs=Inputs(),
        policy=SignalPolicy(),
        clock=lambda: NOW,
    )

    report = service.evaluate_all()

    assert len(store.signals) == 2
    assert len(store.audit) == audit_count
    assert all(
        record.persistence is PersistenceStatus.SKIP_IDEMPOTENT
        for record in report.records
        if record.status is EvaluationStatus.FIRED
    )


def test_new_watermark_creates_new_historical_signal(store: FakeStore) -> None:
    _service(store, Inputs(watermark="import-1")).evaluate_all()

    report = _service(store, Inputs(watermark="import-2")).evaluate_all()

    assert len(store.signals) == 4
    assert all(
        record.persistence is PersistenceStatus.CREATED
        for record in report.records
        if record.status is EvaluationStatus.FIRED
    )


class FailingInputs(Inputs):
    def quality_measurements(self):
        raise RuntimeError("metadata unavailable")


def test_one_evaluator_family_failure_does_not_rollback_other_signals(
    store: FakeStore,
) -> None:
    report = _service(store, FailingInputs()).evaluate_all()

    assert len(store.signals) == 2
    assert any(
        record.evaluator == "DATA_QUALITY_DEGRADED"
        and record.status is EvaluationStatus.FAILED
        for record in report.records
    )

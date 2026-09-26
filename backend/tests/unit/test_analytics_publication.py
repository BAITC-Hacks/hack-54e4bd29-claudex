from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.exceptions import DependencyUnavailableError
from app.security.context import Role
from tests.unit.test_analytics_service import (
    DATE_FILTER,
    FakeAnalyticsRepository,
    FakeCache,
    FakeMetadataRepository,
    context,
    make_service,
)


def setup_service():
    repo = FakeAnalyticsRepository()
    meta = FakeMetadataRepository(())
    cache = FakeCache()
    meta.watermark = replace(
        meta.watermark,
        mapping_version="mapping-1",
        mapping_generation=1,
        mapping_verified=True,
    )
    return repo, meta, cache, make_service(repo, meta, cache)


def test_scoped_health_authority_cannot_gain_global_unmapped_from_role():
    repo, meta, cache, service = setup_service()
    hospital = uuid4()
    service.overview(
        context(Role.HEALTH_AUTHORITY, hospital_ids=(hospital,)), DATE_FILTER
    )
    assert repo.overview_scopes[0].all_canonical is False
    assert repo.overview_scopes[0].include_unmapped is False
    assert repo.overview_scopes[0].canonical_hospital_ids == (hospital,)


def test_revocation_rejects_even_warm_cache():
    repo, meta, cache, service = setup_service()
    ctx = context(Role.HOSPITAL_ANALYST, hospital_ids=(uuid4(),))
    service.overview(ctx, DATE_FILTER)
    assert len(cache.values) == 1
    meta.watermark = replace(
        meta.watermark, mapping_version=None, mapping_generation=2, mapping_verified=False
    )
    with pytest.raises(DependencyUnavailableError):
        service.overview(ctx, DATE_FILTER)
    assert len(repo.overview_scopes) == 1


def test_concurrent_revocation_during_query_blocks_response():
    repo, meta, cache, service = setup_service()
    original = repo.overview

    def revoke(filters, scope):
        result = original(filters, scope)
        meta.watermark = replace(
            meta.watermark,
            mapping_version=None,
            mapping_generation=2,
            mapping_verified=False,
        )
        return result

    repo.overview = revoke
    with pytest.raises(DependencyUnavailableError):
        service.overview(
            context(Role.HOSPITAL_ANALYST, hospital_ids=(uuid4(),)), DATE_FILTER
        )


def test_analytics_query_binds_published_import_allowlist():
    repo, meta, cache, service = setup_service()
    service.overview(context(Role.ADMIN), DATE_FILTER)
    assert repo.overview_scopes[0].published_import_ids == meta.watermark.import_ids
    assert repo.overview_scopes[0].mapping_version == "mapping-1"


def test_load_time_does_not_make_historical_events_current():
    from datetime import date

    from app.business.analytics.service import classify_freshness
    from app.shared.delivery import DeliveryReadiness
    from tests.unit.test_analytics_service import NOW

    state = DeliveryReadiness(
        "REFERRALS",
        confirmed_complete_through=date(2025, 3, 31),
        completeness="COMPLETE",
        cadence_days=1,
    )
    assert classify_freshness(state, NOW) == "STALE"
    assert classify_freshness(replace(state, cadence_days=None), NOW) == "UNKNOWN"
    assert classify_freshness(replace(state, completeness="PARTIAL"), NOW) == "PARTIAL"


def test_snapshot_age_uses_only_imports_with_reviewed_snapshot_semantics():
    from app.shared.analytics_data import RawWaitingSummary
    from app.shared.delivery import DeliveryReadiness
    from tests.unit.test_analytics_service import NOW

    repo, meta, _, service = setup_service()
    reviewed = uuid4()
    meta.watermark = replace(
        meta.watermark, import_ids=(*meta.watermark.import_ids, reviewed)
    )
    meta.delivery_readiness = lambda dataset: DeliveryReadiness(
        dataset,
        published_import_ids=(reviewed,),
        completeness="COMPLETE",
        snapshot_semantics_approved=True,
        snapshot_approved_import_ids=(reviewed,),
    )
    captured = []

    def waiting(_filters, scope):
        captured.append(scope)
        return RawWaitingSummary(NOW, 20, 0, 1, 2, 3, 4)

    repo.waiting_summary = waiting
    service.waiting_summary(context(Role.ADMIN), DATE_FILTER)
    assert captured[0].published_import_ids == meta.watermark.import_ids
    assert captured[0].waiting_import_ids == (reviewed,)
    result = service.waiting_summary(context(Role.ADMIN), DATE_FILTER)
    assert result.snapshot_at == NOW
    assert result.snapshot_semantics_confirmed is True


def test_unconfirmed_waiting_delivery_never_exposes_source_load_as_snapshot():
    from datetime import UTC, datetime

    from app.shared.analytics_data import RawWaitingSummary

    repo, meta, _, service = setup_service()
    imported_at = datetime(2026, 9, 26, tzinfo=UTC)
    scopes = []

    def waiting(_filters, scope):
        scopes.append(scope)
        return RawWaitingSummary(imported_at, 20, 0, 1, 2, 3, 4)

    repo.waiting_summary = waiting
    result = service.waiting_summary(context(Role.ADMIN), DATE_FILTER)
    service.overview(context(Role.ADMIN), DATE_FILTER)
    service.organizations(context(Role.ADMIN), DATE_FILTER, page=1, page_size=20)

    assert result.snapshot_at is None
    assert result.snapshot_semantics_confirmed is False
    assert result.waiting_records.value is None
    assert result.median_days.value is None
    assert scopes[0].waiting_import_ids == ()
    assert repo.overview_scopes[0].waiting_import_ids == ()
    assert repo.organization_calls[0][0].waiting_import_ids == ()


def test_waiting_approval_change_invalidates_overview_cache_with_same_imports():
    from app.shared.delivery import DeliveryReadiness

    repo, meta, cache, service = setup_service()
    approved = [False]
    import_id = meta.watermark.import_ids[0]

    def readiness(dataset):
        return DeliveryReadiness(
            dataset,
            snapshot_approved_import_ids=(import_id,) if approved[0] else (),
        )

    meta.delivery_readiness = readiness
    before = service.overview(context(Role.ADMIN), DATE_FILTER)
    approved[0] = True
    after = service.overview(context(Role.ADMIN), DATE_FILTER)

    assert before.waiting_records.value is None
    assert after.waiting_records.value == 12
    assert len(repo.overview_scopes) == 2
    assert cache.read_keys[0] != cache.read_keys[1]


def test_approved_but_no_eligible_source_snapshot_has_null_snapshot_at():
    from app.shared.analytics_data import RawWaitingSummary
    from app.shared.delivery import DeliveryReadiness

    repo, meta, _, service = setup_service()
    import_id = meta.watermark.import_ids[0]
    meta.delivery_readiness = lambda dataset: DeliveryReadiness(
        dataset, snapshot_approved_import_ids=(import_id,)
    )
    repo.waiting_summary = lambda _filters, _scope: RawWaitingSummary(
        None, 0, 0, None, None, None, None
    )

    result = service.waiting_summary(context(Role.ADMIN), DATE_FILTER)

    assert result.snapshot_at is None
    assert result.snapshot_semantics_confirmed is False
    assert result.waiting_records.value == 0


@pytest.mark.parametrize(
    "role", [Role.HOSPITAL_ANALYST, Role.REGIONAL_ANALYST, Role.HEALTH_AUTHORITY]
)
def test_restricted_quality_never_reads_global_counts(role):
    from unittest.mock import Mock

    repo, meta, _, service = setup_service()
    meta.latest_import_summaries = Mock(return_value=())
    result = service.quality(context(role, hospital_ids=(uuid4(),)))
    assert result.datasets == ()
    assert "GLOBAL_QUALITY_TOTALS_RESTRICTED" in result.metadata.limitations
    meta.latest_import_summaries.assert_not_called()

"""Security and orchestration rules for descriptive analytics."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.business.analytics.contracts import (
    AnalyticsFilter,
    OrganizationIdentity,
)
from app.business.analytics.ports import (
    ImportWatermark,
    QueryScope,
    RawOverview,
)
from app.business.analytics.service import AnalyticsService
from app.core.exceptions import NotFoundError
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role, SecurityContext

NOW = datetime(2026, 5, 14, tzinfo=UTC)
DATE_FILTER = AnalyticsFilter(
    date_from=datetime(2025, 1, 1, tzinfo=UTC),
    date_to=datetime(2025, 3, 31, 23, 59, 59, tzinfo=UTC),
)


class FakeAnalyticsRepository:
    def __init__(self) -> None:
        self.overview_scopes: list[QueryScope] = []

    def overview(self, _filters: AnalyticsFilter, scope: QueryScope) -> RawOverview:
        self.overview_scopes.append(scope)
        return RawOverview(
            referrals_total=20,
            waiting_records=12,
            refusals_total=7,
            hospitalized_total=8,
            unknown_records=1,
            represented_organizations=4,
            represented_regions=2,
        )


class FakeMetadataRepository:
    def __init__(self, hospital_ids: tuple[uuid.UUID, ...]) -> None:
        self.hospital_ids = hospital_ids
        self.watermark = ImportWatermark(
            mapping_version="mapping-1",
            mapping_generation=1,
            mapping_verified=True,
            completed_at=datetime(2026, 5, 13, tzinfo=UTC),
            import_ids=(uuid.UUID("00000000-0000-0000-0000-000000000001"),),
        )

    def delivery_readiness(self, dataset_type):
        from app.shared.delivery import DeliveryReadiness

        return DeliveryReadiness(dataset_type)

    def hospital_ids_for_regions(
        self, region_ids: tuple[uuid.UUID, ...]
    ) -> tuple[uuid.UUID, ...]:
        return self.hospital_ids if region_ids else ()

    def latest_completed_imports(self) -> ImportWatermark:
        return self.watermark

    def hospital_name(self, hospital_id: uuid.UUID) -> str | None:
        return self.hospital_names((hospital_id,)).get(hospital_id)

    def hospital_names(
        self, hospital_ids: tuple[uuid.UUID, ...]
    ) -> dict[uuid.UUID, str]:
        return {hospital_id: f"Hospital {hospital_id}" for hospital_id in hospital_ids}


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, RawOverview] = {}
        self.read_keys: list[str] = []
        self.write_keys: list[str] = []

    def get_overview(self, key: str) -> RawOverview | None:
        self.read_keys.append(key)
        return self.values.get(key)

    def set_overview(self, key: str, value: RawOverview, ttl_seconds: int) -> None:
        assert ttl_seconds == 60
        self.write_keys.append(key)
        self.values[key] = value


def context(
    role: Role,
    *,
    region_ids: tuple[uuid.UUID, ...] = (),
    hospital_ids: tuple[uuid.UUID, ...] = (),
    resolved: bool = True,
) -> SecurityContext:
    return SecurityContext(
        user_id=f"test-{role.value}",
        roles=frozenset({role}),
        scope=DataScope(
            region_ids=frozenset(str(item) for item in region_ids),
            hospital_ids=frozenset(str(item) for item in hospital_ids),
            is_global=role is Role.ADMIN,
            resolved=resolved,
        ),
    )


def make_service(
    repository: FakeAnalyticsRepository,
    metadata: FakeMetadataRepository,
    cache: FakeCache,
) -> AnalyticsService:
    return AnalyticsService(
        repository=repository,
        metadata_repository=metadata,
        cache=cache,
        authorization=AuthorizationService(),
        min_cell_size=10,
        cache_ttl_seconds=60,
        clock=lambda: NOW,
    )


def test_hospital_role_queries_only_explicit_canonical_hospitals() -> None:
    hospital_id = uuid.uuid4()
    repository = FakeAnalyticsRepository()
    service = make_service(repository, FakeMetadataRepository(()), FakeCache())

    service.overview(
        context(Role.HOSPITAL_ANALYST, hospital_ids=(hospital_id,)), DATE_FILTER
    )

    assert [
        replace(item, mapping_version=None, published_import_ids=None)
        for item in repository.overview_scopes
    ] == [
        QueryScope(
            canonical_hospital_ids=(hospital_id,),
            all_canonical=False,
            include_unmapped=False,
        )
    ]


def test_regional_scope_is_resolved_to_hospitals_and_excludes_unmapped() -> None:
    region_id = uuid.uuid4()
    hospital_ids = (uuid.uuid4(), uuid.uuid4())
    repository = FakeAnalyticsRepository()
    service = make_service(repository, FakeMetadataRepository(hospital_ids), FakeCache())

    service.overview(context(Role.REGIONAL_ANALYST, region_ids=(region_id,)), DATE_FILTER)

    assert replace(
        repository.overview_scopes[0], mapping_version=None, published_import_ids=None
    ) == QueryScope(
        canonical_hospital_ids=hospital_ids,
        all_canonical=False,
        include_unmapped=False,
    )


def test_health_authority_can_review_unmapped_but_canonical_scope_stays_bounded() -> None:
    region_id = uuid.uuid4()
    hospital_id = uuid.uuid4()
    repository = FakeAnalyticsRepository()
    service = make_service(
        repository, FakeMetadataRepository((hospital_id,)), FakeCache()
    )

    service.overview(context(Role.HEALTH_AUTHORITY, region_ids=(region_id,)), DATE_FILTER)

    assert replace(
        repository.overview_scopes[0], mapping_version=None, published_import_ids=None
    ) == QueryScope(
        canonical_hospital_ids=(hospital_id,),
        all_canonical=False,
        include_unmapped=False,
    )


def test_unresolved_scope_fails_closed() -> None:
    repository = FakeAnalyticsRepository()
    service = make_service(repository, FakeMetadataRepository(()), FakeCache())

    service.overview(context(Role.REGIONAL_ANALYST, resolved=False), DATE_FILTER)

    assert replace(
        repository.overview_scopes[0], mapping_version=None, published_import_ids=None
    ) == QueryScope(
        canonical_hospital_ids=(), all_canonical=False, include_unmapped=False
    )


def test_source_organization_is_hidden_from_hospital_role() -> None:
    service = make_service(
        FakeAnalyticsRepository(), FakeMetadataRepository(()), FakeCache()
    )
    source_identity = OrganizationIdentity.source("a" * 64)

    with pytest.raises(NotFoundError):
        service.require_organization_access(
            context(Role.HOSPITAL_MANAGER, hospital_ids=(uuid.uuid4(),)),
            source_identity,
        )


def test_cache_key_isolated_by_scope_and_invalidated_by_import_watermark() -> None:
    first_hospital = uuid.uuid4()
    second_hospital = uuid.uuid4()
    repository = FakeAnalyticsRepository()
    metadata = FakeMetadataRepository(())
    cache = FakeCache()
    service = make_service(repository, metadata, cache)

    service.overview(
        context(Role.HOSPITAL_ANALYST, hospital_ids=(first_hospital,)), DATE_FILTER
    )
    service.overview(
        context(Role.HOSPITAL_ANALYST, hospital_ids=(second_hospital,)), DATE_FILTER
    )
    metadata.watermark = ImportWatermark(
        mapping_version="mapping-1",
        mapping_generation=1,
        mapping_verified=True,
        completed_at=datetime(2026, 5, 14, tzinfo=UTC),
        import_ids=(uuid.UUID("00000000-0000-0000-0000-000000000002"),),
    )
    service.overview(
        context(Role.HOSPITAL_ANALYST, hospital_ids=(first_hospital,)), DATE_FILTER
    )

    assert len(set(cache.read_keys)) == 3
    assert len(repository.overview_scopes) == 3


def test_cached_overview_avoids_second_clickhouse_query() -> None:
    repository = FakeAnalyticsRepository()
    cache = FakeCache()
    service = make_service(repository, FakeMetadataRepository(()), cache)
    admin = context(Role.ADMIN)

    first = service.overview(admin, DATE_FILTER)
    second = service.overview(admin, DATE_FILTER)

    assert first.referrals_total.value == 20
    assert second.referrals_total.value == 20
    assert len(repository.overview_scopes) == 1
    assert cache.read_keys[0] == cache.read_keys[1]

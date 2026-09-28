"""Пагинация, сортировка и область данных справочников."""

from __future__ import annotations

import pytest

from app.business.hospitals.service import (
    HOSPITAL_DEFAULT_SORT,
    HOSPITAL_SORT_FIELDS,
    HospitalService,
)
from app.business.regions.service import (
    REGION_DEFAULT_SORT,
    REGION_SORT_FIELDS,
    RegionService,
)
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.shared.filters import HospitalFilter
from app.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    PageRequest,
    build_page_request,
)
from tests.fakes import (
    FakeStore,
    make_context,
    make_hospital,
    make_region,
    unit_of_work_factory,
)

# --- Пагинация --------------------------------------------------------------


def build(**overrides):
    params = {
        "page": 1,
        "page_size": DEFAULT_PAGE_SIZE,
        "sort_by": None,
        "sort_desc": True,
        "allowed_sort_fields": frozenset({"name", "created_at"}),
        "default_sort_field": "name",
    }
    params.update(overrides)
    return build_page_request(**params)


def test_default_page_request() -> None:
    request = build()
    assert request.page == 1
    assert request.sort_by == "name"
    assert request.offset == 0


def test_offset_follows_page() -> None:
    assert build(page=3, page_size=25).offset == 50


@pytest.mark.parametrize("page_size", [0, -1, MAX_PAGE_SIZE + 1, 1_000_000])
def test_page_size_beyond_limit_is_rejected(page_size: int) -> None:
    """Предел применяется отказом, а не молчаливым усечением.

    Клиент должен узнать, что его запрос не выполнен так, как он
    рассчитывал, вместо того чтобы получить неполные данные.
    """
    with pytest.raises(ValidationError) as error:
        build(page_size=page_size)
    assert error.value.details["max_page_size"] == MAX_PAGE_SIZE


def test_page_below_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build(page=0)


def test_unknown_sort_field_is_rejected() -> None:
    """Произвольное имя поля извне в запрос не попадает."""
    with pytest.raises(ValidationError) as error:
        build(sort_by="password; DROP TABLE signals")
    assert error.value.details["allowed"] == ["created_at", "name"]


def test_allowed_sort_field_passes() -> None:
    assert build(sort_by="created_at").sort_by == "created_at"


def test_has_next_reflects_remaining_items() -> None:
    request = PageRequest(page=1, page_size=20, sort_by="name", sort_desc=False)
    assert Page.build([], 100, request).has_next
    assert not Page.build([], 20, request).has_next


def test_sort_allowlists_are_not_empty() -> None:
    assert REGION_DEFAULT_SORT in REGION_SORT_FIELDS
    assert HOSPITAL_DEFAULT_SORT in HOSPITAL_SORT_FIELDS


# --- Область данных справочников --------------------------------------------


@pytest.fixture
def directory(store: FakeStore):
    class Directory:
        pass

    d = Directory()
    d.region_a = store.add_region(make_region("R-A", "Регион А"))
    d.region_b = store.add_region(make_region("R-B", "Регион Б"))
    d.hospital_a1 = store.add_hospital(make_hospital(d.region_a, "H-A1", "А1"))
    d.hospital_a2 = store.add_hospital(make_hospital(d.region_a, "H-A2", "А2"))
    d.hospital_b1 = store.add_hospital(make_hospital(d.region_b, "H-B1", "Б1"))
    return d


@pytest.fixture
def regions(store: FakeStore) -> RegionService:
    return RegionService(unit_of_work_factory(store), AuthorizationService())


@pytest.fixture
def hospitals(store: FakeStore) -> HospitalService:
    return HospitalService(unit_of_work_factory(store), AuthorizationService())


PAGE = PageRequest(page=1, page_size=20, sort_by="name", sort_desc=False)


def test_regional_user_sees_only_own_region(regions: RegionService, directory) -> None:
    context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(
            region_ids=frozenset({str(directory.region_a.id)}), resolved=True
        ),
    )
    page = regions.list_regions(context, PAGE)
    assert [item.code for item in page.items] == ["R-A"]


def test_regional_user_cannot_open_other_region(
    regions: RegionService, directory
) -> None:
    context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(
            region_ids=frozenset({str(directory.region_a.id)}), resolved=True
        ),
    )
    with pytest.raises(NotFoundError):
        regions.get_region(context, directory.region_b.id)


def test_hospital_role_cannot_list_regions(regions: RegionService, directory) -> None:
    """Право на чтение регионов ролям организации не выдано."""
    context = make_context(
        roles={Role.HOSPITAL_MANAGER},
        scope=DataScope(
            hospital_ids=frozenset({str(directory.hospital_a1.id)}), resolved=True
        ),
    )
    with pytest.raises(ForbiddenError):
        regions.list_regions(context, PAGE)


def test_hospital_user_sees_only_own_hospital(
    hospitals: HospitalService, directory
) -> None:
    context = make_context(
        roles={Role.HOSPITAL_MANAGER},
        scope=DataScope(
            hospital_ids=frozenset({str(directory.hospital_a1.id)}), resolved=True
        ),
    )
    page = hospitals.list_hospitals(context, HospitalFilter(), PAGE)
    assert [item.code for item in page.items] == ["H-A1"]


def test_hospital_user_cannot_open_neighbour_in_same_region(
    hospitals: HospitalService, directory
) -> None:
    """Доступ к одной организации не открывает соседнюю по региону."""
    context = make_context(
        roles={Role.HOSPITAL_MANAGER},
        scope=DataScope(
            hospital_ids=frozenset({str(directory.hospital_a1.id)}), resolved=True
        ),
    )
    with pytest.raises(NotFoundError):
        hospitals.get_hospital(context, directory.hospital_a2.id)


def test_regional_user_sees_all_hospitals_of_region(
    hospitals: HospitalService, directory
) -> None:
    context = make_context(
        roles={Role.REGIONAL_ANALYST},
        scope=DataScope(
            region_ids=frozenset({str(directory.region_a.id)}), resolved=True
        ),
    )
    page = hospitals.list_hospitals(context, HospitalFilter(), PAGE)
    assert {item.code for item in page.items} == {"H-A1", "H-A2"}


def test_pagination_limits_returned_rows(hospitals: HospitalService, directory) -> None:
    context = make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())
    page = hospitals.list_hospitals(
        context,
        HospitalFilter(),
        PageRequest(page=1, page_size=2, sort_by="name", sort_desc=False),
    )
    assert len(page.items) == 2
    assert page.total == 3
    assert page.has_next

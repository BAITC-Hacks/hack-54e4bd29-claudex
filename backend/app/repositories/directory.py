"""Репозитории справочников.

Репозиторий выполняет запросы и не содержит правил. Область данных
приходит явным параметром: догадываться о ней он не должен.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.directory import Hospital, Region
from app.repositories.scope import hospital_clause, region_clause
from app.security.context import DataScope
from app.shared.filters import HospitalFilter
from app.shared.pagination import PageRequest

type RegionPage = tuple[list[Region], int]
type HospitalPage = tuple[list[Hospital], int]

# Отображение разрешённых имён сортировки на столбцы. Имя, которого
# здесь нет, до запроса не доходит: перечень проверяет бизнес-слой.
REGION_SORT_COLUMNS = {
    "code": Region.code,
    "name": Region.name,
    "created_at": Region.created_at,
}

HOSPITAL_SORT_COLUMNS = {
    "code": Hospital.code,
    "name": Hospital.name,
    "created_at": Hospital.created_at,
}


def apply_sort[T: tuple[Any, ...]](
    statement: Select[T], page: PageRequest, columns: Mapping[str, Any]
) -> Select[T]:
    column = columns.get(page.sort_by or "")
    if column is None:
        return statement
    ordering = column.desc() if page.sort_desc else column.asc()
    return statement.order_by(ordering)


def count_of(session: Session, statement: Select[Any]) -> int:
    """Общее число строк выборки до применения страницы."""
    subquery = statement.order_by(None).subquery()
    total = session.scalar(select(func.count()).select_from(subquery))
    return int(total or 0)


class SqlAlchemyRegionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, region_id: uuid.UUID, scope: DataScope) -> Region | None:
        statement = select(Region).where(Region.id == region_id, region_clause(scope))
        return self._session.scalars(statement).first()

    def list(self, scope: DataScope, page: PageRequest) -> RegionPage:
        statement = select(Region).where(region_clause(scope))
        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, REGION_SORT_COLUMNS)
        rows = self._session.scalars(
            statement.offset(page.offset).limit(page.limit)
        ).all()
        return list(rows), total


class SqlAlchemyHospitalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, hospital_id: uuid.UUID, scope: DataScope) -> Hospital | None:
        statement = select(Hospital).where(
            Hospital.id == hospital_id, hospital_clause(scope)
        )
        return self._session.scalars(statement).first()

    def list(
        self, scope: DataScope, filters: HospitalFilter, page: PageRequest
    ) -> HospitalPage:
        statement = select(Hospital).where(hospital_clause(scope))

        if filters.region_id is not None:
            statement = statement.where(Hospital.region_id == filters.region_id)
        if filters.is_active is not None:
            statement = statement.where(Hospital.is_active == filters.is_active)

        total = count_of(self._session, statement)
        statement = apply_sort(statement, page, HOSPITAL_SORT_COLUMNS)
        rows = self._session.scalars(
            statement.offset(page.offset).limit(page.limit)
        ).all()
        return list(rows), total

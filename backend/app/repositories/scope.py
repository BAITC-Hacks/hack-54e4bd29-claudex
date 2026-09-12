"""Построение условий области данных для SQL-запросов.

Область данных превращается в условие WHERE здесь и только здесь.
Дублирование этой логики по репозиториям — самый вероятный способ
однажды забыть её в одном запросе и получить утечку.

Три случая, и все три обязаны обрабатываться явно:

* глобальная область — ограничение не накладывается;
* неразрешённая область — запрет; отсутствие сведений об области
  трактуется как отказ, а не как разрешение;
* заданная область — принадлежность организации или её региону.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, false, or_, select, true

from app.models.directory import Hospital, Region
from app.security.context import DataScope


def _as_uuids(values: frozenset[str]) -> list[uuid.UUID]:
    """Преобразовать идентификаторы области в UUID.

    Непригодные значения отбрасываются: строка области приходит из базы,
    и ошибка разбора не должна расширять доступ.
    """
    parsed: list[uuid.UUID] = []
    for value in values:
        try:
            parsed.append(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError):
            continue
    return parsed


def hospital_clause(scope: DataScope) -> ColumnElement[bool]:
    """Условие видимости организации."""
    if scope.is_global:
        return true()
    if not scope.resolved:
        return false()

    hospital_ids = _as_uuids(scope.hospital_ids)
    region_ids = _as_uuids(scope.region_ids)
    if not hospital_ids and not region_ids:
        return false()

    conditions: list[ColumnElement[bool]] = []
    if hospital_ids:
        conditions.append(Hospital.id.in_(hospital_ids))
    if region_ids:
        conditions.append(Hospital.region_id.in_(region_ids))
    return or_(*conditions)


def region_clause(scope: DataScope) -> ColumnElement[bool]:
    """Условие видимости региона.

    Пользователь, ограниченный организациями, видит регион, которому
    эти организации принадлежат: без него карточка организации
    осталась бы без названия региона.
    """
    if scope.is_global:
        return true()
    if not scope.resolved:
        return false()

    hospital_ids = _as_uuids(scope.hospital_ids)
    region_ids = _as_uuids(scope.region_ids)
    if not hospital_ids and not region_ids:
        return false()

    conditions: list[ColumnElement[bool]] = []
    if region_ids:
        conditions.append(Region.id.in_(region_ids))
    if hospital_ids:
        conditions.append(
            Region.id.in_(select(Hospital.region_id).where(Hospital.id.in_(hospital_ids)))
        )
    return or_(*conditions)

"""Правила работы со справочником медицинских организаций."""

from __future__ import annotations

import uuid

from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import NotFoundError
from app.models.directory import Hospital
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.filters import HospitalFilter
from app.shared.pagination import Page, PageRequest

HOSPITAL_SORT_FIELDS: frozenset[str] = frozenset({"code", "name", "created_at"})
HOSPITAL_DEFAULT_SORT = "name"


class HospitalService:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, authorization: AuthorizationService
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization

    def list_hospitals(
        self, context: SecurityContext, filters: HospitalFilter, page: PageRequest
    ) -> Page[Hospital]:
        self._authz.require_permission(context, Permission.HOSPITAL_READ)
        with self._uow_factory() as uow:
            items, total = uow.hospitals.list(context.scope, filters, page)
        return Page.build(items, total, page)

    def get_hospital(self, context: SecurityContext, hospital_id: uuid.UUID) -> Hospital:
        """Организация вне области данных неотличима от отсутствующей.

        Это основная защита от перебора идентификаторов: различие ответов
        раскрывало бы состав организаций региона.
        """
        self._authz.require_permission(context, Permission.HOSPITAL_READ)
        with self._uow_factory() as uow:
            hospital = uow.hospitals.get(hospital_id, context.scope)
        if hospital is None:
            raise NotFoundError("Медицинская организация не найдена")
        return hospital

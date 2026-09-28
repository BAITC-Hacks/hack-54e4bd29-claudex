"""Правила работы со справочником регионов."""

from __future__ import annotations

import uuid

from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import NotFoundError
from app.models.directory import Region
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.pagination import Page, PageRequest

REGION_SORT_FIELDS: frozenset[str] = frozenset({"code", "name", "created_at"})
REGION_DEFAULT_SORT = "name"


class RegionService:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, authorization: AuthorizationService
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization

    def list_regions(self, context: SecurityContext, page: PageRequest) -> Page[Region]:
        self._authz.require_permission(context, Permission.REGION_READ)
        with self._uow_factory() as uow:
            items, total = uow.regions.list(context.scope, page)
        return Page.build(items, total, page)

    def get_region(self, context: SecurityContext, region_id: uuid.UUID) -> Region:
        """Регион вне области данных неотличим от отсутствующего."""
        self._authz.require_permission(context, Permission.REGION_READ)
        with self._uow_factory() as uow:
            region = uow.regions.get(region_id, context.scope)
        if region is None:
            raise NotFoundError("Регион не найден")
        return region

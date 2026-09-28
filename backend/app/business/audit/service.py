"""Чтение журнала аудита.

Журнал сам является чувствительным объектом: он показывает, кто и чем
занимался. Поэтому его чтение требует отдельного права и ограничено
областью данных пользователя (SECURITY.md, раздел 9).
"""

from __future__ import annotations

from app.business.ports import UnitOfWorkFactory
from app.models.audit import AuditEvent
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.filters import AuditFilter
from app.shared.pagination import Page, PageRequest

AUDIT_SORT_FIELDS: frozenset[str] = frozenset({"created_at"})
AUDIT_DEFAULT_SORT = "created_at"


class AuditService:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, authorization: AuthorizationService
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization

    def list_events(
        self, context: SecurityContext, filters: AuditFilter, page: PageRequest
    ) -> Page[AuditEvent]:
        self._authz.require_permission(context, Permission.AUDIT_READ)
        with self._uow_factory() as uow:
            items, total = uow.audit.list(context.scope, filters, page)
        return Page.build(items, total, page)

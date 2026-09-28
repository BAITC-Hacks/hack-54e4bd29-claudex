"""Чтение истории загрузок.

Отделено от запуска импорта намеренно. Чтение нужно API, запуск — командной
строке, и зависимости у них разные: чтобы показать список поставок,
библиотека разбора файлов не нужна. Держать их в одном сервисе означало бы
тащить polars и разбор CSV в образ, который смотрит наружу.
"""

from __future__ import annotations

import uuid

from app.business.ports import UnitOfWorkFactory
from app.core.exceptions import NotFoundError
from app.models.data_import import DataImport
from app.models.enums import DatasetType
from app.models.quality import DataQualityResult
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission
from app.shared.pagination import Page, PageRequest


class DataImportQueryService:
    """История загрузок и отчёты о качестве. Только чтение."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, authorization: AuthorizationService
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization

    def list_imports(
        self,
        context: SecurityContext,
        page: PageRequest,
        dataset_type: DatasetType | None = None,
    ) -> Page[DataImport]:
        """Страница импортов, новые сверху.

        Области данных здесь нет намеренно: поставка относится к системе
        целиком, а не к территории. Доступ ограничен правом.
        """
        self._authz.require_permission(context, Permission.DATA_IMPORT_READ)
        with self._uow_factory() as uow:
            items, total = uow.data_imports.list(
                page, dataset_type.value if dataset_type else None
            )
            return Page.build(items, total, page)

    def get_import(self, context: SecurityContext, import_id: uuid.UUID) -> DataImport:
        self._authz.require_permission(context, Permission.DATA_IMPORT_READ)
        with self._uow_factory() as uow:
            data_import = uow.data_imports.get(import_id)
            if data_import is None:
                raise NotFoundError("Импорт не найден")
            return data_import

    def get_quality(
        self, context: SecurityContext, import_id: uuid.UUID
    ) -> list[DataQualityResult]:
        """Замечания о качестве поставки.

        Отчёт содержит счётчики и коды правил. Значений из выгрузки в нём
        нет: его читают люди без доступа к медицинским данным.
        """
        self._authz.require_permission(context, Permission.DATA_IMPORT_READ)
        with self._uow_factory() as uow:
            if uow.data_imports.get(import_id) is None:
                raise NotFoundError("Импорт не найден")
            return uow.data_quality.list_for_import(import_id)

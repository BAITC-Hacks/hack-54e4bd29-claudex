"""Репозитории отчёта о качестве и карантина.

Записи о качестве только добавляются и читаются. Изменять их незачем:
отчёт относится к конкретной поставке, и переписанный отчёт перестаёт
описывать то, что тогда произошло.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.quality import DataQualityResult, QuarantineBatch


class SqlAlchemyDataQualityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, results: Sequence[DataQualityResult]) -> int:
        if not results:
            return 0
        self._session.add_all(list(results))
        self._session.flush()
        return len(results)

    def list_for_import(self, import_id: uuid.UUID) -> list[DataQualityResult]:
        statement = (
            select(DataQualityResult)
            .where(DataQualityResult.data_import_id == import_id)
            .order_by(
                DataQualityResult.severity,
                DataQualityResult.rule_code,
            )
        )
        return list(self._session.scalars(statement).all())


class SqlAlchemyQuarantineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, batches: Sequence[QuarantineBatch]) -> int:
        if not batches:
            return 0
        self._session.add_all(list(batches))
        self._session.flush()
        return len(batches)

    def list_for_import(self, import_id: uuid.UUID) -> list[QuarantineBatch]:
        statement = (
            select(QuarantineBatch)
            .where(QuarantineBatch.data_import_id == import_id)
            .order_by(QuarantineBatch.created_at)
        )
        return list(self._session.scalars(statement).all())

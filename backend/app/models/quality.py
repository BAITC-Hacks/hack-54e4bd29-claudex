"""Замечания о качестве загруженных данных.

Одна запись — одно правило по одному столбцу с числом затронутых строк.
Строчку на каждую отклонённую запись здесь не пишут: полтора миллиона
записей об ошибках сделали бы таблицу нечитаемой и заодно перенесли бы
в PostgreSQL те самые данные, ради защиты которых существует карантин.

Сообщение содержит счётчики и никогда — значения из источника. Отчёт
о качестве читают люди без доступа к медицинским данным.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import QualitySeverity


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"
    __table_args__ = (
        Index("ix_data_quality_results_data_import_id", "data_import_id"),
        Index("ix_data_quality_results_severity", "severity"),
        CheckConstraint(
            "affected_rows >= 0",
            name="ck_data_quality_results_affected_rows_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    data_import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_imports.id", ondelete="CASCADE"),
        nullable=False,
    )

    validation_level: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[QualitySeverity] = mapped_column(String(16), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    affected_rows: Mapped[int] = mapped_column(nullable=False, default=0)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class QuarantineBatch(Base):
    """Ссылка на отложенную в карантин партию.

    Сами строки лежат в объектном хранилище в зоне ограниченного доступа.
    Здесь только адрес и причины: так карантин остаётся находимым, но
    не попадает в базу приложения и не выдаётся аналитическим API.
    """

    __tablename__ = "quarantine_batches"
    __table_args__ = (Index("ix_quarantine_batches_data_import_id", "data_import_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    data_import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    rows: Mapped[int] = mapped_column(nullable=False, default=0)
    reason_codes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

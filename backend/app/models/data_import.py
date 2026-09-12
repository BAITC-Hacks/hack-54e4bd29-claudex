"""Импорт выгрузки.

Состав полей и жизненный цикл заданы ADR-0010. Реальный разбор данных
относится к PHASE 3: здесь только запись об операции и её идемпотентность.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import DataImportStatus


class DataImport(Base):
    __tablename__ = "data_imports"
    __table_args__ = (
        # Ключ идемпотентности. Контрольная сумма считается по содержимому,
        # а не по имени: переименованный файл — тот же файл.
        UniqueConstraint(
            "dataset_type", "file_hash", name="uq_data_imports_dataset_type_file_hash"
        ),
        Index("ix_data_imports_status_created_at", "status", "created_at"),
        Index("ix_data_imports_file_hash", "file_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    status: Mapped[DataImportStatus] = mapped_column(
        String(16), nullable=False, default=DataImportStatus.PENDING
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Краткая причина для пользователя. Трассировка остаётся в журнале,
    # связанном по request_id.
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

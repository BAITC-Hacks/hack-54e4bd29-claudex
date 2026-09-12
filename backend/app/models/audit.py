"""Неизменяемый журнал аудита.

Записи только добавляются. Методов изменения и удаления нет ни в модели,
ни в репозитории; на уровне СУБД ограничение прав вводится отдельно
(SECURITY.md, раздел 7 в DATABASE.md).

В журнал не попадают персональные и медицинские данные: он фиксирует,
кто и что сделал с объектом, а не содержимое объекта.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import AuditAction, AuditEntityType


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        # История конкретного объекта.
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        # Лента журнала.
        Index("ix_audit_events_created_at", "created_at"),
        # Действия конкретного пользователя.
        Index("ix_audit_events_actor_user_id_created_at", "actor_user_id", "created_at"),
        # Восстановление цепочки одной операции.
        Index("ix_audit_events_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Пустой актор означает системную операцию, а не анонимного пользователя.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[AuditEntityType] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Связывает запись с HTTP-запросом и с журналом приложения.
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Состояния до и после в структурированном виде. Медицинских
    # и персональных данных здесь быть не должно.
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

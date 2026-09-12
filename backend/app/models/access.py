"""Пользователи и области данных.

MedSignal не хранит пароли: аутентификацию выполняет Keycloak (ADR-0009).
Таблица пользователей — проекция субъекта провайдера на область данных,
которой управляет администратор MedSignal.

Область данных не берётся из токена: изменение, внесённое администратором,
должно действовать немедленно, а не после перевыпуска токена.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow
from app.models.enums import DataScopeType


class User(Base):
    """Проекция субъекта провайдера идентификации.

    Учётных данных не содержит и содержать не может.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Идентификатор субъекта из токена (claim `sub`). Связывает запись
    # с учётной записью Keycloak, не дублируя её.
    external_subject: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    scopes: Mapped[list[UserDataScope]] = relationship(
        back_populates="user", lazy="selectin", cascade="all, delete-orphan"
    )


class UserDataScope(Base):
    """Строка области данных пользователя.

    Хранение областей строками, а не полями, позволяет задавать
    нестандартные сочетания без изменения схемы: координатор может
    получить доступ к нескольким организациям из разных регионов.
    """

    __tablename__ = "user_data_scopes"
    __table_args__ = (
        Index("ix_user_data_scopes_user_id", "user_id"),
        UniqueConstraint(
            "user_id",
            "scope_type",
            "region_id",
            "hospital_id",
            name="uq_user_data_scopes_user_id_scope_type_region_id_hospital_id",
        ),
        # Строка области обязана указывать ровно на тот объект, который
        # соответствует её типу. Иначе появляется область без смысла.
        CheckConstraint(
            "(scope_type = 'GLOBAL'"
            " AND region_id IS NULL AND hospital_id IS NULL)"
            " OR (scope_type = 'REGION'"
            " AND region_id IS NOT NULL AND hospital_id IS NULL)"
            " OR (scope_type = 'HOSPITAL'"
            " AND hospital_id IS NOT NULL AND region_id IS NULL)",
            name="ck_user_data_scopes_target_matches_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[DataScopeType] = mapped_column(String(16), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="CASCADE"), nullable=True
    )
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped[User] = relationship(back_populates="scopes", lazy="raise")

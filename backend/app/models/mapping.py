"""Сопоставление значений источника со справочниками.

Data Audit показал, что одна и та же организация в разных выгрузках
названа по-разному: где-то полным юридическим наименованием, где-то
четырёхсимвольным кодом, и множества значений не пересекаются вовсе.
То же с регионами: числовые коды против наименований.

Отсюда конструкция: значение из источника хранится как есть, а связь
со справочником — отдельная запись, у которой есть состояние и способ
подтверждения. Пока связи нет, факт всё равно загружается и помечается
несопоставленным. Альтернатива — угадать соответствие по похожести —
означала бы приписать нагрузку не той организации, и обнаружилось бы
это не скоро.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.enums import MappingMethod, MappingStatus


class OrganizationAlias(Base):
    """Значение организации из источника и его связь со справочником."""

    __tablename__ = "organization_aliases"
    __table_args__ = (
        # Ключ — система-источник и нормализованное значение. Одна и та же
        # строка из двух разных систем может означать разные организации.
        UniqueConstraint(
            "source_system",
            "identity_space",
            "normalized_value",
            name="uq_organization_aliases_identity",
        ),
        Index("ix_organization_aliases_mapping_status", "mapping_status"),
        Index("ix_organization_aliases_hospital_id", "hospital_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hospitals.id", ondelete="SET NULL"),
        nullable=True,
    )
    identity_space: Mapped[str] = mapped_column(
        String(96),
        nullable=False,
        default="LEGACY_UNRESOLVED",
        server_default="LEGACY_UNRESOLVED",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)

    mapping_status: Mapped[MappingStatus] = mapped_column(
        String(16), nullable=False, default=MappingStatus.UNMAPPED
    )
    mapping_method: Mapped[MappingMethod | None] = mapped_column(
        String(32), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurrences: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class RegionAlias(Base):
    """Значение региона из источника и его связь со справочником."""

    __tablename__ = "region_aliases"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "identity_space",
            "normalized_value",
            name="uq_region_aliases_identity",
        ),
        Index("ix_region_aliases_mapping_status", "mapping_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True
    )
    identity_space: Mapped[str] = mapped_column(
        String(96),
        nullable=False,
        default="LEGACY_UNRESOLVED",
        server_default="LEGACY_UNRESOLVED",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)

    mapping_status: Mapped[MappingStatus] = mapped_column(
        String(16), nullable=False, default=MappingStatus.UNMAPPED
    )
    mapping_method: Mapped[MappingMethod | None] = mapped_column(
        String(32), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurrences: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ProfileAlias(Base):
    """Профиль койки из источника.

    Справочника профилей в системе пока нет: Data Audit показал, что
    наименование профиля в направлениях и код профиля в очереди
    не пересекаются ни одним значением. Поэтому canonical_profile_id
    остаётся пустым, а таблица накапливает встреченные значения — это
    и есть материал для будущего официального сопоставления.
    """

    __tablename__ = "profile_aliases"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "normalized_value",
            name="uq_profile_aliases_source_system_normalized_value",
        ),
        Index("ix_profile_aliases_mapping_status", "mapping_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)

    mapping_status: Mapped[MappingStatus] = mapped_column(
        String(16), nullable=False, default=MappingStatus.UNMAPPED
    )
    mapping_method: Mapped[MappingMethod | None] = mapped_column(
        String(32), nullable=True
    )

    first_seen_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurrences: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class MappingState(Base):
    __tablename__ = "mapping_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_generation: Mapped[int | None] = mapped_column(Integer)
    active_version: Mapped[str | None] = mapped_column(String(128))


class MappingRevision(Base):
    __tablename__ = "mapping_revisions"
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    digest: Mapped[str] = mapped_column(String(64))
    rows: Mapped[list] = mapped_column(JSONB)
    actor: Mapped[str] = mapped_column(String(256))
    evidence_ref: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

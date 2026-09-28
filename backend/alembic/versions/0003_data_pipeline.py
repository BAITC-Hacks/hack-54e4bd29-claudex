"""Конвейер загрузки данных (PHASE 3B).

Добавляет:

* статистику к записи об импорте — прочитано, принято, отклонено,
  загружено, предупреждений, длительность;
* сопоставление значений источника со справочниками организаций,
  регионов и профилей;
* замечания о качестве загрузки;
* ссылки на партии, отложенные в карантин.

Аналитические таблицы здесь не создаются: они относятся к ClickHouse
и описаны версионированными файлами в `database/clickhouse/migrations`.

Revision ID: 0003_data_pipeline
Revises: 0002_domain_foundation
Create Date: PHASE 3B

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_data_pipeline"
down_revision: str | None = "0002_domain_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _alias_table(
    name: str,
    canonical_column: sa.Column[object],
    unique_name: str,
    status_index: str,
) -> None:
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        canonical_column,
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("mapping_status", sa.String(length=16), nullable=False),
        sa.Column("mapping_method", sa.String(length=32), nullable=True),
        sa.Column("first_seen_import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["first_seen_import_id"],
            ["data_imports.id"],
            name=f"fk_{name}_first_seen_import_id_data_imports",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
        sa.UniqueConstraint("source_system", "normalized_value", name=unique_name),
    )
    op.create_index(status_index, name, ["mapping_status"], unique=False)


def upgrade() -> None:
    # --- Статистика импорта -------------------------------------------------
    for column, kind in (
        ("rows_read", sa.BigInteger()),
        ("rows_valid", sa.BigInteger()),
        ("rows_rejected", sa.BigInteger()),
        ("rows_loaded", sa.BigInteger()),
        ("warnings_count", sa.BigInteger()),
        ("source_size_bytes", sa.BigInteger()),
    ):
        op.add_column(
            "data_imports",
            sa.Column(column, kind, nullable=False, server_default="0"),
        )
    op.add_column(
        "data_imports",
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
    )

    # --- Сопоставления ------------------------------------------------------
    _alias_table(
        "organization_aliases",
        sa.Column("hospital_id", postgresql.UUID(as_uuid=True), nullable=True),
        "uq_organization_aliases_source_system_normalized_value",
        "ix_organization_aliases_mapping_status",
    )
    op.create_foreign_key(
        "fk_organization_aliases_hospital_id_hospitals",
        "organization_aliases",
        "hospitals",
        ["hospital_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("organization_aliases", sa.Column("note", sa.Text(), nullable=True))
    op.create_index(
        "ix_organization_aliases_hospital_id",
        "organization_aliases",
        ["hospital_id"],
        unique=False,
    )

    _alias_table(
        "region_aliases",
        sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True),
        "uq_region_aliases_source_system_normalized_value",
        "ix_region_aliases_mapping_status",
    )
    op.create_foreign_key(
        "fk_region_aliases_region_id_regions",
        "region_aliases",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("region_aliases", sa.Column("note", sa.Text(), nullable=True))

    _alias_table(
        "profile_aliases",
        sa.Column("canonical_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        "uq_profile_aliases_source_system_normalized_value",
        "ix_profile_aliases_mapping_status",
    )

    # --- Качество -----------------------------------------------------------
    op.create_table(
        "data_quality_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("validation_level", sa.String(length=16), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("column_name", sa.String(length=128), nullable=True),
        sa.Column("affected_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "affected_rows >= 0",
            name="ck_data_quality_results_affected_rows_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["data_import_id"],
            ["data_imports.id"],
            name="fk_data_quality_results_data_import_id_data_imports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_quality_results"),
    )
    op.create_index(
        "ix_data_quality_results_data_import_id",
        "data_quality_results",
        ["data_import_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_results_severity",
        "data_quality_results",
        ["severity"],
        unique=False,
    )

    # --- Карантин -----------------------------------------------------------
    op.create_table(
        "quarantine_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_type", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reason_codes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_import_id"],
            ["data_imports.id"],
            name="fk_quarantine_batches_data_import_id_data_imports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quarantine_batches"),
    )
    op.create_index(
        "ix_quarantine_batches_data_import_id",
        "quarantine_batches",
        ["data_import_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quarantine_batches_data_import_id", table_name="quarantine_batches")
    op.drop_table("quarantine_batches")

    op.drop_index("ix_data_quality_results_severity", table_name="data_quality_results")
    op.drop_index(
        "ix_data_quality_results_data_import_id", table_name="data_quality_results"
    )
    op.drop_table("data_quality_results")

    op.drop_index("ix_profile_aliases_mapping_status", table_name="profile_aliases")
    op.drop_table("profile_aliases")

    op.drop_index("ix_region_aliases_mapping_status", table_name="region_aliases")
    op.drop_table("region_aliases")

    op.drop_index(
        "ix_organization_aliases_hospital_id", table_name="organization_aliases"
    )
    op.drop_index(
        "ix_organization_aliases_mapping_status", table_name="organization_aliases"
    )
    op.drop_table("organization_aliases")

    for column in (
        "duration_seconds",
        "source_size_bytes",
        "warnings_count",
        "rows_loaded",
        "rows_rejected",
        "rows_valid",
        "rows_read",
    ):
        op.drop_column("data_imports", column)

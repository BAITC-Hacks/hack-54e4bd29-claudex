"""Phase 5A short-horizon referral forecasting metadata.

Revision ID: 0004_ml_foundation
Revises: 0003_data_pipeline
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_ml_foundation"
down_revision: str | None = "0003_data_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("mlflow_run_id", sa.String(length=128), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_period_start", sa.Date(), nullable=False),
        sa.Column("training_period_end", sa.Date(), nullable=False),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("forecast_horizon_days", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "baseline_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "validation_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "dataset_watermark", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("selection_rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_versions"),
        sa.UniqueConstraint("version", name="uq_model_versions_version"),
        sa.UniqueConstraint("mlflow_run_id", name="uq_model_versions_mlflow_run_id"),
    )
    op.create_index("ix_model_versions_target", "model_versions", ["target"])

    op.alter_column("forecasts", "hospital_id", nullable=True)
    op.add_column(
        "forecasts", sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "forecasts",
        sa.Column(
            "scope_type",
            sa.String(length=16),
            nullable=False,
            server_default="HOSPITAL",
        ),
    )
    op.add_column(
        "forecasts",
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    for column, default in (
        ("selected_model", "legacy"),
        ("baseline_model", "legacy"),
        ("feature_schema_version", "legacy_v0"),
    ):
        op.add_column(
            "forecasts",
            sa.Column(
                column, sa.String(length=64), nullable=False, server_default=default
            ),
        )
    for column, default in (
        ("dataset_watermark", "'{}'::jsonb"),
        ("validation_metrics", "'{}'::jsonb"),
        ("baseline_metrics", "'{}'::jsonb"),
        ("validation_folds", "'[]'::jsonb"),
    ):
        op.add_column(
            "forecasts",
            sa.Column(
                column,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text(default),
            ),
        )
    op.add_column("forecasts", sa.Column("forecast_start", sa.Date(), nullable=True))
    op.add_column("forecasts", sa.Column("forecast_end", sa.Date(), nullable=True))
    op.create_foreign_key(
        "fk_forecasts_region_id_regions",
        "forecasts",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_forecasts_model_version_id_model_versions",
        "forecasts",
        "model_versions",
        ["model_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_forecasts_scope_target",
        "forecasts",
        "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
        "(scope_type = 'REGION' AND hospital_id IS NULL AND region_id IS NOT NULL) OR "
        "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
    )
    op.create_index(
        "ix_forecasts_scope_target_generated_at",
        "forecasts",
        ["scope_type", "target", "generated_at"],
    )
    op.create_index("ix_forecasts_model_version_id", "forecasts", ["model_version_id"])

    for column in (
        "scope_type",
        "selected_model",
        "baseline_model",
        "feature_schema_version",
        "dataset_watermark",
        "validation_metrics",
        "baseline_metrics",
        "validation_folds",
    ):
        op.alter_column("forecasts", column, server_default=None)

    op.create_table(
        "forecast_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("predicted_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 4), nullable=False),
        sa.ForeignKeyConstraint(
            ["forecast_id"],
            ["forecasts.id"],
            name="fk_forecast_points_forecast_id_forecasts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_forecast_points"),
        sa.UniqueConstraint(
            "forecast_id",
            "forecast_date",
            name="uq_forecast_points_forecast_date",
        ),
    )
    op.create_index("ix_forecast_points_forecast_id", "forecast_points", ["forecast_id"])


def downgrade() -> None:
    op.drop_index("ix_forecast_points_forecast_id", table_name="forecast_points")
    op.drop_table("forecast_points")
    op.drop_index("ix_forecasts_model_version_id", table_name="forecasts")
    op.drop_index("ix_forecasts_scope_target_generated_at", table_name="forecasts")
    op.drop_constraint("ck_forecasts_scope_target", "forecasts", type_="check")
    op.drop_constraint(
        "fk_forecasts_model_version_id_model_versions", "forecasts", type_="foreignkey"
    )
    op.drop_constraint("fk_forecasts_region_id_regions", "forecasts", type_="foreignkey")
    for column in (
        "forecast_end",
        "forecast_start",
        "validation_folds",
        "baseline_metrics",
        "validation_metrics",
        "dataset_watermark",
        "feature_schema_version",
        "baseline_model",
        "selected_model",
        "model_version_id",
        "scope_type",
        "region_id",
    ):
        op.drop_column("forecasts", column)
    op.alter_column("forecasts", "hospital_id", nullable=False)
    op.drop_index("ix_model_versions_target", table_name="model_versions")
    op.drop_table("model_versions")

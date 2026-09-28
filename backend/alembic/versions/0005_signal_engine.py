"""Phase 6 explicit Signal scope, evidence and Incident workflow.

Revision ID: 0005_signal_engine
Revises: 0004_ml_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_signal_engine"
down_revision: str | None = "0004_ml_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("signals", "hospital_id", nullable=True)
    op.add_column(
        "signals",
        sa.Column(
            "scope_type", sa.String(length=16), nullable=False, server_default="HOSPITAL"
        ),
    )
    op.add_column(
        "signals", sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "signals", sa.Column("evaluation_period_start", sa.Date(), nullable=True)
    )
    op.add_column("signals", sa.Column("evaluation_period_end", sa.Date(), nullable=True))
    op.add_column(
        "signals", sa.Column("reference_period_start", sa.Date(), nullable=True)
    )
    op.add_column("signals", sa.Column("reference_period_end", sa.Date(), nullable=True))
    op.add_column("signals", sa.Column("actual_value", sa.Numeric(20, 4), nullable=True))
    op.add_column(
        "signals", sa.Column("baseline_value", sa.Numeric(20, 4), nullable=True)
    )
    op.add_column(
        "signals", sa.Column("delta_absolute", sa.Numeric(20, 4), nullable=True)
    )
    op.add_column("signals", sa.Column("delta_percent", sa.Numeric(12, 4), nullable=True))
    op.add_column(
        "signals",
        sa.Column(
            "rule_code",
            sa.String(length=96),
            nullable=False,
            server_default="LEGACY_SIGNAL",
        ),
    )
    op.add_column(
        "signals",
        sa.Column(
            "rule_version",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_v0",
        ),
    )
    for column in ("rule_config", "evidence", "data_watermark"):
        op.add_column(
            "signals",
            sa.Column(
                column,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    op.add_column(
        "signals",
        sa.Column(
            "source", sa.String(length=64), nullable=False, server_default="LEGACY"
        ),
    )
    op.add_column(
        "signals",
        sa.Column(
            "data_current", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("signals", sa.Column("dedup_key", sa.String(length=64), nullable=True))
    op.add_column(
        "signals", sa.Column("closure_disposition", sa.String(length=16), nullable=True)
    )
    op.execute("UPDATE signals SET dedup_key = 'legacy:' || id::text")
    op.alter_column("signals", "dedup_key", nullable=False)
    op.create_foreign_key(
        "fk_signals_region_id_regions",
        "signals",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_signals_scope_target",
        "signals",
        "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
        "(scope_type = 'REGION' AND hospital_id IS NULL AND region_id IS NOT NULL) OR "
        "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
    )
    op.create_unique_constraint("uq_signals_dedup_key", "signals", ["dedup_key"])
    op.create_index(
        "ix_signals_scope_status_detected_at",
        "signals",
        ["scope_type", "region_id", "hospital_id", "status", "detected_at"],
    )

    op.alter_column("incidents", "hospital_id", nullable=True)
    op.add_column(
        "incidents",
        sa.Column(
            "scope_type", sa.String(length=16), nullable=False, server_default="HOSPITAL"
        ),
    )
    op.add_column(
        "incidents", sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "incidents", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "fk_incidents_region_id_regions",
        "incidents",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_incidents_assigned_user_id_users",
        "incidents",
        "users",
        ["assigned_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_incidents_created_by_users",
        "incidents",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_incidents_scope_target",
        "incidents",
        "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
        "(scope_type = 'REGION' AND hospital_id IS NULL AND region_id IS NOT NULL) OR "
        "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
    )
    op.create_index(
        "ix_incidents_scope_status",
        "incidents",
        ["scope_type", "region_id", "hospital_id", "status"],
    )

    for column in (
        "scope_type",
        "rule_code",
        "rule_version",
        "rule_config",
        "evidence",
        "source",
        "data_watermark",
        "data_current",
    ):
        op.alter_column("signals", column, server_default=None)
    op.alter_column("incidents", "scope_type", server_default=None)
    op.alter_column("incidents", "version", server_default=None)


def downgrade() -> None:
    # 0004 requires a hospital for every Signal and Incident. Phase 6 GLOBAL
    # and REGION rows cannot be represented after downgrade, so remove those
    # Phase-6-only records explicitly before restoring NOT NULL. Related
    # actions cascade and signal->incident links use SET NULL.
    op.execute("DELETE FROM signals WHERE hospital_id IS NULL")
    op.execute("DELETE FROM incidents WHERE hospital_id IS NULL")

    op.drop_index("ix_incidents_scope_status", table_name="incidents")
    op.drop_constraint("ck_incidents_scope_target", "incidents", type_="check")
    op.drop_constraint("fk_incidents_created_by_users", "incidents", type_="foreignkey")
    op.drop_constraint(
        "fk_incidents_assigned_user_id_users", "incidents", type_="foreignkey"
    )
    op.drop_constraint("fk_incidents_region_id_regions", "incidents", type_="foreignkey")
    for column in (
        "version",
        "created_by",
        "assigned_user_id",
        "region_id",
        "scope_type",
    ):
        op.drop_column("incidents", column)
    op.alter_column("incidents", "hospital_id", nullable=False)

    op.drop_index("ix_signals_scope_status_detected_at", table_name="signals")
    op.drop_constraint("uq_signals_dedup_key", "signals", type_="unique")
    op.drop_constraint("ck_signals_scope_target", "signals", type_="check")
    op.drop_constraint("fk_signals_region_id_regions", "signals", type_="foreignkey")
    for column in (
        "closure_disposition",
        "dedup_key",
        "data_current",
        "data_watermark",
        "source",
        "evidence",
        "rule_config",
        "rule_version",
        "rule_code",
        "delta_percent",
        "delta_absolute",
        "baseline_value",
        "actual_value",
        "reference_period_end",
        "reference_period_start",
        "evaluation_period_end",
        "evaluation_period_start",
        "region_id",
        "scope_type",
    ):
        op.drop_column("signals", column)
    op.alter_column("signals", "hospital_id", nullable=False)

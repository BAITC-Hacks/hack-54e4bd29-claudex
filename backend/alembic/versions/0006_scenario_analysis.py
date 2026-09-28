"""Phase 7 immutable scenario analysis.

Revision ID: 0006_scenario_analysis
Revises: 0005_signal_engine
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_scenario_analysis"
down_revision: str | None = "0005_signal_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_empty_scenarios(operation: str) -> None:
    connection = op.get_bind()
    count = connection.execute(sa.text("SELECT count(*) FROM scenarios")).scalar_one()
    if count:
        raise RuntimeError(
            f"Cannot {operation} Phase 7 scenario schema with {count} legacy rows; "
            "an explicit provenance migration is required"
        )


def upgrade() -> None:
    # Phase 2 exposed no scenario write API and the accepted database is empty.
    # Fabricating provenance for unknown legacy rows would violate auditability.
    _require_empty_scenarios("upgrade")

    op.drop_constraint("fk_scenarios_signal_id_signals", "scenarios", type_="foreignkey")
    op.alter_column("scenarios", "signal_id", new_column_name="source_signal_id")
    op.alter_column("scenarios", "assumptions", new_column_name="limitations_snapshot")
    op.alter_column("scenarios", "hospital_id", nullable=True)

    op.add_column("scenarios", sa.Column("scope_type", sa.String(16), nullable=False))
    op.add_column(
        "scenarios", sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "scenarios",
        sa.Column("source_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("scenarios", sa.Column("baseline_type", sa.String(16), nullable=False))
    op.add_column(
        "scenarios", sa.Column("baseline_value", sa.Numeric(20, 4), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("baseline_period_start", sa.Date(), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("baseline_period_end", sa.Date(), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("assumption_value", sa.Numeric(6, 4), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("calculated_value", sa.Numeric(20, 4), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("delta_absolute", sa.Numeric(20, 4), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("delta_percent", sa.Numeric(6, 4), nullable=False)
    )
    op.add_column(
        "scenarios",
        sa.Column(
            "data_watermark",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "scenarios",
        sa.Column("forecast_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("scenarios", sa.Column("model_version", sa.String(128), nullable=True))
    op.add_column("scenarios", sa.Column("forecast_status", sa.String(16), nullable=True))
    op.add_column(
        "scenarios",
        sa.Column("baseline_freshness_status", sa.String(16), nullable=False),
    )
    op.add_column(
        "scenarios", sa.Column("formula_version", sa.String(64), nullable=False)
    )
    op.add_column(
        "scenarios", sa.Column("limitations_version", sa.String(64), nullable=False)
    )
    op.add_column(
        "scenarios",
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_scenarios_source_signal_id_signals",
        "scenarios",
        "signals",
        ["source_signal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scenarios_source_incident_id_incidents",
        "scenarios",
        "incidents",
        ["source_incident_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scenarios_region_id_regions",
        "scenarios",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_scenarios_forecast_id_forecasts",
        "scenarios",
        "forecasts",
        ["forecast_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_scenarios_scope_target",
        "scenarios",
        "(scope_type = 'GLOBAL' AND hospital_id IS NULL AND region_id IS NULL) OR "
        "(scope_type = 'REGION' AND hospital_id IS NULL AND region_id IS NOT NULL) OR "
        "(scope_type = 'HOSPITAL' AND hospital_id IS NOT NULL AND region_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_scenarios_baseline_positive", "scenarios", "baseline_value > 0"
    )
    op.create_unique_constraint(
        "uq_scenarios_actor_request",
        "scenarios",
        ["created_by", "client_request_id"],
    )
    op.create_index(
        "ix_scenarios_scope_created_at",
        "scenarios",
        ["scope_type", "region_id", "hospital_id", "created_at"],
    )
    op.create_index("ix_scenarios_source_signal_id", "scenarios", ["source_signal_id"])
    op.create_index(
        "ix_scenarios_source_incident_id", "scenarios", ["source_incident_id"]
    )
    op.execute("ALTER TABLE scenarios ALTER COLUMN data_watermark DROP DEFAULT")


def downgrade() -> None:
    _require_empty_scenarios("downgrade")
    op.drop_index("ix_scenarios_source_incident_id", table_name="scenarios")
    op.drop_index("ix_scenarios_source_signal_id", table_name="scenarios")
    op.drop_index("ix_scenarios_scope_created_at", table_name="scenarios")
    op.drop_constraint("uq_scenarios_actor_request", "scenarios", type_="unique")
    op.drop_constraint("ck_scenarios_baseline_positive", "scenarios", type_="check")
    op.drop_constraint("ck_scenarios_scope_target", "scenarios", type_="check")
    for name in (
        "fk_scenarios_forecast_id_forecasts",
        "fk_scenarios_region_id_regions",
        "fk_scenarios_source_incident_id_incidents",
        "fk_scenarios_source_signal_id_signals",
    ):
        op.drop_constraint(name, "scenarios", type_="foreignkey")
    for column in (
        "client_request_id",
        "limitations_version",
        "formula_version",
        "baseline_freshness_status",
        "forecast_status",
        "model_version",
        "forecast_id",
        "data_watermark",
        "delta_percent",
        "delta_absolute",
        "calculated_value",
        "assumption_value",
        "baseline_period_end",
        "baseline_period_start",
        "baseline_value",
        "baseline_type",
        "source_incident_id",
        "region_id",
        "scope_type",
    ):
        op.drop_column("scenarios", column)
    op.alter_column("scenarios", "hospital_id", nullable=False)
    op.alter_column("scenarios", "limitations_snapshot", new_column_name="assumptions")
    op.alter_column("scenarios", "source_signal_id", new_column_name="signal_id")
    op.create_foreign_key(
        "fk_scenarios_signal_id_signals",
        "scenarios",
        "signals",
        ["signal_id"],
        ["id"],
        ondelete="SET NULL",
    )

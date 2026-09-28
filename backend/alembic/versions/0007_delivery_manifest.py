"""Reviewed delivery manifests. Legacy imports retain NULL linkage."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0007_delivery_manifest"
down_revision = "0006_scenario_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deliveries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_id", sa.String(128), nullable=False, unique=True),
        sa.Column("dataset_type", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(128), nullable=False),
        sa.Column("manifest", pg.JSONB(), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("snapshot_date", sa.Date()),
        sa.Column("confirmed_complete_through", sa.Date()),
        sa.Column("cadence_days", sa.Integer()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64)),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(256), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "delivery_parts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("deliveries.id"),
            nullable=False,
        ),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "delivery_id", "file_hash", name="uq_delivery_parts_delivery_hash"
        ),
    )
    op.add_column("data_imports", sa.Column("delivery_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_data_imports_delivery_id_deliveries",
        "data_imports",
        "deliveries",
        ["delivery_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_data_imports_delivery_id_deliveries", "data_imports", type_="foreignkey"
    )
    op.drop_column("data_imports", "delivery_id")
    op.drop_table("delivery_parts")
    op.drop_table("deliveries")

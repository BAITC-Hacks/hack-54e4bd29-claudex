"""Exact identities, immutable decisions and versioned publication pointer."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0008_mapping_versions"
down_revision = "0007_delivery_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organization_aliases", "region_aliases"):
        op.add_column(
            table,
            sa.Column(
                "identity_space",
                sa.String(96),
                nullable=False,
                server_default="LEGACY_UNRESOLVED",
            ),
        )
        op.add_column(
            table, sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )
        op.drop_constraint(
            f"uq_{table}_source_system_normalized_value", table, type_="unique"
        )
        op.create_unique_constraint(
            f"uq_{table}_identity",
            table,
            ["source_system", "identity_space", "normalized_value"],
        )
    op.create_table(
        "mapping_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("active_generation", sa.Integer()),
        sa.Column("active_version", sa.String(128)),
    )
    op.execute("INSERT INTO mapping_state (id,generation) VALUES (1,0)")
    op.create_table(
        "mapping_revisions",
        sa.Column("version", sa.String(128), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False, unique=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("rows", pg.JSONB(), nullable=False),
        sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    # Returning to ambiguous keys can merge identities -> None: require operator migration instead.
    raise RuntimeError(
        "Mapping identity downgrade requires explicit reviewed reconciliation"
    )

"""Системная таблица операций (PHASE 1).

Единственная таблица фундамента. Реализует жизненный цикл долгих
операций из ADR-0010: PENDING -> RUNNING -> COMPLETED | FAILED.
Доменные таблицы появляются в PHASE 2.

Revision ID: 0001_system_operations
Revises:
Create Date: PHASE 1

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_system_operations"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_system_operations_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_system_operations"),
    )
    op.create_index(
        "ix_system_operations_status_created_at",
        "system_operations",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_system_operations_request_id", "system_operations", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_system_operations_request_id", table_name="system_operations")
    op.drop_index(
        "ix_system_operations_status_created_at", table_name="system_operations"
    )
    op.drop_table("system_operations")

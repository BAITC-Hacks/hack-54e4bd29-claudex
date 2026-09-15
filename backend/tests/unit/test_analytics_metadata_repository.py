"""Regression tests for analytics metadata across multipart imports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.models.data_import import DataImport
from app.models.enums import DataImportStatus
from app.repositories.analytics_metadata import SqlAlchemyAnalyticsMetadataRepository


def _completed_import(*, completed_at: datetime, rows_loaded: int) -> DataImport:
    return DataImport(
        id=uuid.uuid4(),
        dataset_type="REFERRALS",
        source="IS_BG",
        file_name=f"part-{rows_loaded}.xlsx",
        file_hash=f"hash-{rows_loaded}",
        status=DataImportStatus.COMPLETED,
        completed_at=completed_at,
        rows_loaded=rows_loaded,
        rows_rejected=0,
        warnings_count=rows_loaded // 10,
    )


def test_import_summary_aggregates_all_completed_dataset_parts(
    monkeypatch,
) -> None:
    newest = datetime(2026, 4, 2, tzinfo=UTC)
    rows = [
        _completed_import(completed_at=newest, rows_loaded=200),
        _completed_import(completed_at=newest - timedelta(days=1), rows_loaded=100),
    ]
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = session
    repository = SqlAlchemyAnalyticsMetadataRepository(session_factory)
    monkeypatch.setattr(repository, "_completed_rows", lambda: rows)

    (summary,) = repository.latest_import_summaries()

    assert summary.import_id == rows[0].id
    assert summary.completed_at == newest
    assert summary.rows_loaded == 300
    assert summary.warnings_count == 30

"""ORM metadata must describe the already accepted PostgreSQL schema."""

from __future__ import annotations

from sqlalchemy import BigInteger

from app.models.analytics import Forecast
from app.models.data_import import DataImport
from app.models.mapping import OrganizationAlias, ProfileAlias, RegionAlias
from app.models.quality import DataQualityResult, QuarantineBatch


def _server_default(model: type, column_name: str) -> str | None:
    default = model.__table__.columns[column_name].server_default
    return None if default is None else str(default.arg)


def test_pipeline_counter_metadata_matches_migration_0003() -> None:
    for name in (
        "rows_read",
        "rows_valid",
        "rows_rejected",
        "rows_loaded",
        "warnings_count",
        "source_size_bytes",
    ):
        column = DataImport.__table__.columns[name]
        assert isinstance(column.type, BigInteger)
        assert _server_default(DataImport, name) == "0"

    assert _server_default(DataImport, "duration_seconds") == "0"
    assert isinstance(
        DataQualityResult.__table__.columns["affected_rows"].type, BigInteger
    )
    assert _server_default(DataQualityResult, "affected_rows") == "0"
    assert isinstance(QuarantineBatch.__table__.columns["rows"].type, BigInteger)
    assert _server_default(QuarantineBatch, "rows") == "0"
    assert _server_default(QuarantineBatch, "reason_codes") == ""


def test_mapping_occurrence_defaults_match_migration_0003() -> None:
    for model in (OrganizationAlias, RegionAlias, ProfileAlias):
        assert _server_default(model, "occurrences") == "0"


def test_forecast_indexes_match_migration_0004() -> None:
    indexes = {index.name for index in Forecast.__table__.indexes}
    assert "ix_forecasts_model_version_id" in indexes
    assert "ix_forecasts_scope_target_generated_at" in indexes

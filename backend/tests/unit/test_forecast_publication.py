"""Forecast lineage must exclude completed files in unpublished deliveries."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import NotFoundError
from app.models import Base
from app.models.data_import import DataImport
from app.models.delivery import Delivery
from app.models.enums import DataImportStatus, DatasetType
from app.repositories.forecast_metadata import SqlAlchemyForecastMetadataRepository


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    yield sessions
    engine.dispose()


def seed(sessions, delivery_status, suffix):
    with sessions.begin() as session:
        delivery_id = None
        if delivery_status:
            delivery_id = uuid4()
            session.add(
                Delivery(
                    id=delivery_id,
                    delivery_id=suffix,
                    dataset_type="REFERRALS",
                    source_system="IS_BG",
                    contract_version="synthetic-v1",
                    manifest={},
                    manifest_digest="a" * 64,
                    mode="EVENT",
                    status=delivery_status,
                    evidence_ref="synthetic",
                    approved_by="synthetic-reviewer",
                )
            )
            session.flush()
        record = DataImport(
            id=uuid4(),
            dataset_type=DatasetType.REFERRALS,
            source="IS_BG",
            file_name=f"synthetic-{suffix}.csv",
            file_hash=suffix,
            status=DataImportStatus.COMPLETED,
            delivery_id=delivery_id,
            completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        session.add(record)
        return record.id


def test_forecast_lineage_only_published_or_legacy_imports(store):
    legacy = seed(store, None, "legacy")
    published = seed(store, "PUBLISHED", "published")
    hidden = seed(store, "APPROVED", "partial")
    result = SqlAlchemyForecastMetadataRepository(store).referral_watermark()
    assert set(result.import_ids) == {legacy, published}
    assert set(
        SqlAlchemyForecastMetadataRepository(store).referral_history_import_ids()
    ) == {legacy, published}
    assert hidden not in result.import_ids
    assert set(result.file_hashes) == {"legacy", "published"}


def test_unpublished_only_is_not_a_forecast_dataset(store):
    seed(store, "APPROVED", "partial")
    assert SqlAlchemyForecastMetadataRepository(store).referral_history_import_ids() == ()
    with pytest.raises(NotFoundError):
        SqlAlchemyForecastMetadataRepository(store).referral_watermark()

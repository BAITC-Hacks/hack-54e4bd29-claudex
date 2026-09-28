from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.models.enums import DatasetType
from tests.fakes import FakeStore
from tests.unit.test_import_service import (
    FakePipeline,
    FakeSourceFile,
    admin_context,
)


def test_new_unapproved_import_cannot_write_facts(tmp_path):
    pipeline = FakePipeline([FakeSourceFile("synthetic.csv", tmp_path / "synthetic.csv")])
    from app.business.ingestion.service import ImportService
    from app.security.authorization import AuthorizationService
    from tests.fakes import unit_of_work_factory

    service = ImportService(
        unit_of_work_factory(FakeStore()), AuthorizationService(), pipeline
    )
    with pytest.raises(ValidationError, match="APPROVED_MANIFEST_REQUIRED"):
        service.import_dataset(admin_context(), DatasetType.REFERRALS)
    assert pipeline.processed == []

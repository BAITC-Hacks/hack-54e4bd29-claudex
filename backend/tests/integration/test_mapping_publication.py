"""Native repository transactions and synthetic projection fault boundaries."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.business.mapping.service import MappingService
from app.core.exceptions import ConflictError
from app.models.directory import Hospital, Region
from app.models.mapping import ProfileAlias
from app.repositories.clickhouse_mapping import ClickHouseMappingRepository
from app.security.authorization import AuthorizationService
from app.shared.mapping import MappingSnapshot
from tests.integration.test_delivery_import import database as database
from tests.unit.test_import_service import admin_context


class SyntheticProjection:
    def __init__(self):
        self.rows = []
        self.fail_after_insert = False
        self.fail_read = False

    def query(self, _sql, parameters):
        if self.fail_read:
            raise RuntimeError("synthetic read failure")
        return Mock(
            result_rows=[r[1:] for r in self.rows if r[0] == parameters["version"]]
        )

    def insert(self, _table, rows, column_names):
        assert column_names == [
            "version",
            "kind",
            "identity_space",
            "source_key",
            "canonical_id",
        ]
        self.rows.extend(rows)
        if self.fail_after_insert:
            raise RuntimeError("synthetic lost acknowledgement")


def test_lost_insert_ack_retry_verifies_without_duplicates():
    client = SyntheticProjection()
    repo = ClickHouseMappingRepository(client)
    snapshot = MappingSnapshot.from_rows(
        "mapping-1", [("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "code", str(uuid4()))]
    )
    client.fail_after_insert = True
    with pytest.raises(RuntimeError):
        repo.publish(snapshot)
    client.fail_after_insert = False
    repo.publish(snapshot)
    repo.publish(snapshot)
    assert len(client.rows) == 1


def test_corrupt_candidate_does_not_publish():
    client = SyntheticProjection()
    repo = ClickHouseMappingRepository(client)
    snapshot = MappingSnapshot.from_rows(
        "mapping-1", [("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", "code", str(uuid4()))]
    )
    client.rows = [("mapping-1", *snapshot.rows()[0])] * 2
    with pytest.raises(ConflictError, match="CORRUPT"):
        repo.publish(snapshot)


def test_operator_review_lists_exact_identity_and_approval_evidence(
    database,  # noqa: F811 - imported pytest fixture
):
    sessions, factory = database
    service = MappingService(factory, AuthorizationService(), Mock())
    context = replace(admin_context(), internal_user_id=None)
    region_id, hospital_id = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(Region(id=region_id, code="synthetic-region", name="Synthetic"))
        session.add(
            Hospital(
                id=hospital_id,
                code="synthetic-hospital",
                name="Synthetic hospital",
                region_id=region_id,
            )
        )
        session.add(
            ProfileAlias(
                source_system="ИС БГ",
                source_value="synthetic-profile",
                normalized_value="synthetic-profile",
            )
        )
    alias_id = service.register(
        context,
        kind="ORGANIZATION",
        source_system="IS_BG",
        identity_space="IS_BG:REFERRALS:RECEIVING",
        source_key="synthetic-org-code",
    )
    unmapped, total = service.review(context, kind="ORGANIZATION", status="UNMAPPED")
    assert total == 1
    assert unmapped[0].source_identifier == "synthetic-org-code"
    assert unmapped[0].canonical_id is None
    version = service.approve(context, alias_id, hospital_id, "synthetic-evidence", 0)
    mapped, total = service.review(context, kind="ORGANIZATION", status="MAPPED")
    assert total == 1
    assert mapped[0].canonical_id == hospital_id
    assert mapped[0].approved_mapping_version == version
    assert mapped[0].approved_by == context.user_id
    assert mapped[0].approved_at is not None
    assert mapped[0].evidence_ref == "synthetic-evidence"
    profiles, total = service.review(context, kind="PROFILE", status="UNMAPPED")
    assert total == 1
    assert profiles[0].canonical_id is None
    assert profiles[0].approved_by is None


def test_identity_spaces_revocation_stale_version_and_audit_rollback(
    database,  # noqa: F811 - imported pytest fixture
    monkeypatch,
):
    sessions, factory = database
    client = SyntheticProjection()
    service = MappingService(
        factory, AuthorizationService(), ClickHouseMappingRepository(client)
    )
    context = replace(admin_context(), internal_user_id=None)
    h1, h2, r1 = uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(Region(id=r1, code="synthetic-r", name="Synthetic"))
        session.add_all(
            [
                Hospital(id=h1, code="synthetic-h1", name="Synthetic one", region_id=r1),
                Hospital(id=h2, code="synthetic-h2", name="Synthetic two", region_id=r1),
            ]
        )
    a = service.register(
        context,
        kind="ORGANIZATION",
        source_system="IS_BG",
        identity_space="IS_BG:REFERRALS:RECEIVING",
        source_key="same-code",
    )
    b = service.register(
        context,
        kind="ORGANIZATION",
        source_system="IS_BG",
        identity_space="IS_BG:WAITING:DESTINATION",
        source_key="same-code",
    )
    v1 = service.approve(context, a, h1, "synthetic-evidence", 0)
    service.publish(context, v1)
    v2 = service.approve(context, b, h2, "synthetic-evidence", 0)
    with factory() as uow:
        assert not uow.mappings.readiness().verified
    client.fail_read = True
    with pytest.raises(RuntimeError):
        service.publish(context, v2)
    with factory() as uow:
        assert not uow.mappings.readiness().verified
    client.fail_read = False
    snapshot = service.publish(context, v2)
    assert len(snapshot.organizations) == 2
    assert {m.hospital_id for m in snapshot.organizations} == {h1, h2}
    with pytest.raises(ConflictError, match="STALE"):
        service.revoke(context, a, "withdrawn", 0)
    v3 = service.revoke(context, a, "withdrawn", 1)
    with factory() as uow:
        ready = uow.mappings.readiness()
        assert ready.version is None and not ready.verified
    snapshot = service.publish(context, v3)
    assert tuple(m.hospital_id for m in snapshot.organizations) == (h2,)
    from app.repositories.audit import SqlAlchemyAuditRepository

    def fail_audit(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(SqlAlchemyAuditRepository, "append", fail_audit)
    with pytest.raises(RuntimeError):
        service.revoke(context, b, "withdrawn", 1)
    with factory() as uow:
        assert uow.mappings.readiness().version == v3
        assert uow.mappings.get_alias(b).hospital_id == h2

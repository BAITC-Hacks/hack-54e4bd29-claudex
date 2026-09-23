from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.business.mapping.service import MappingService
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role, SecurityContext

HOSPITAL = uuid4()


def ctx(role=Role.ADMIN):
    return SecurityContext(
        user_id="synthetic-reviewer",
        roles=frozenset({role}),
        scope=DataScope.global_scope(),
    )


@pytest.fixture
def setup():
    alias = SimpleNamespace(
        id=uuid4(),
        identity_space="IS_BG:REFERRALS:RECEIVING",
        normalized_value="code",
        hospital_id=None,
        mapping_status="UNMAPPED",
        mapping_method=None,
        version=0,
    )
    repo = Mock()
    repo.get_alias.return_value = alias
    repo.target_exists.return_value = True
    repo.record_decision.return_value = "mapping-1"
    uow = Mock(mappings=repo)

    @contextmanager
    def factory():
        yield uow

    service = MappingService(factory, AuthorizationService(), Mock())
    return service, repo, uow, alias


def test_normal_user_cannot_approve(setup):
    service, repo, _, alias = setup
    with pytest.raises(ForbiddenError):
        service.approve(
            ctx(Role.HOSPITAL_ANALYST), alias.id, HOSPITAL, "synthetic-evidence", 0
        )
    repo.lock.assert_not_called()


def test_unknown_hospital_is_not_found(setup):
    service, repo, _, alias = setup
    repo.target_exists.return_value = False
    with pytest.raises(NotFoundError):
        service.approve(ctx(), alias.id, HOSPITAL, "evidence", 0)


@pytest.mark.parametrize(
    ("field", "value", "exception", "message"),
    [
        ("version", 2, ConflictError, "STALE_MAPPING_VERSION"),
        ("mapping_status", "REVIEW_REQUIRED", ConflictError, "REVIEW_REQUIRED"),
        (
            "identity_space",
            "LEGACY_UNRESOLVED",
            ValidationError,
            "IDENTITY_SPACE_UNCONFIRMED",
        ),
    ],
)
def test_ambiguous_stale_and_conflicted_mapping_denied(
    setup, field, value, exception, message
):
    service, _, uow, alias = setup
    setattr(alias, field, value)
    with pytest.raises(exception, match=message):
        service.approve(ctx(), alias.id, HOSPITAL, "evidence", 0)
    uow.commit.assert_not_called()


def test_evidence_required_and_audit_atomic(setup):
    service, repo, uow, alias = setup
    with pytest.raises(ValidationError):
        service.approve(ctx(), alias.id, HOSPITAL, "", 0)
    assert service.approve(ctx(), alias.id, HOSPITAL, "evidence", 0) == "mapping-1"
    assert alias.hospital_id == HOSPITAL
    uow.audit.append.assert_called_once()
    uow.commit.assert_called_once()
    assert repo.record_decision.call_args.kwargs["actor"] == "synthetic-reviewer"


def test_revoke_invalidates_entitlement_in_same_transaction(setup):
    service, repo, uow, alias = setup
    alias.hospital_id = HOSPITAL
    alias.mapping_status = "MAPPED"
    service.revoke(ctx(), alias.id, "withdrawn evidence", 0)
    assert alias.hospital_id is None
    assert alias.mapping_status == "UNMAPPED"
    repo.record_decision.assert_called_once()
    uow.audit.append.assert_called_once()
    uow.commit.assert_called_once()


def test_publication_failure_never_switches_active_pointer(setup):
    service, repo, uow, _ = setup
    service._projection.publish.side_effect = RuntimeError("synthetic boundary failure")
    with pytest.raises(RuntimeError):
        service.publish(ctx(), "mapping-1")
    repo.activate.assert_not_called()
    uow.commit.assert_not_called()

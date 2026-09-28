"""The local synthetic seed may follow an authenticated test login."""

from __future__ import annotations

import uuid
from unittest.mock import Mock

from app.models.access import User
from seeds.dev_seed import _ensure_user


def test_seed_reuses_user_created_by_oidc_login() -> None:
    existing = User(
        id=uuid.uuid4(), external_subject="synthetic-subject", display_name="test"
    )
    session = Mock()
    session.query.return_value.filter_by.return_value.one_or_none.return_value = existing

    result = _ensure_user(session, "synthetic-subject", "synthetic display")

    assert result is existing
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_seed_creates_user_when_subject_is_absent() -> None:
    session = Mock()
    session.query.return_value.filter_by.return_value.one_or_none.return_value = None

    result = _ensure_user(session, "synthetic-subject", "synthetic display")

    assert result.external_subject == "synthetic-subject"
    session.add.assert_called_once_with(result)
    session.flush.assert_called_once_with()

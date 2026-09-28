"""Журнал не содержит чувствительных значений.

Требование SECURITY.md, раздел 9.2. Проверка существует потому, что
полагаться на дисциплину разработчиков в этом вопросе нельзя.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import REDACTED, JsonFormatter, RedactingFilter, redact
from app.core.request_context import request_id_scope


@pytest.mark.parametrize(
    "key",
    [
        "Authorization",
        "authorization",
        "X-Authorization",
        "cookie",
        "Set-Cookie",
        "password",
        "user_password",
        "access_token",
        "refresh-token",
        "api_key",
        "client_secret",
        "private_key",
        "session_id",
        "pseudonym_salt",
        "iin",
        "patient_name",
        "phone_number",
        "birth_date",
    ],
)
def test_sensitive_keys_are_redacted(key: str) -> None:
    assert redact({key: "чувствительное значение"})[key] == REDACTED


@pytest.mark.parametrize("key", ["hospital_id", "region_code", "duration_ms", "status"])
def test_ordinary_keys_are_preserved(key: str) -> None:
    assert redact({key: "значение"})[key] == "значение"


def test_redaction_is_recursive() -> None:
    payload = {
        "outer": {"headers": {"Authorization": "Bearer abc"}, "count": 3},
        "items": [{"token": "xyz"}, {"ok": True}],
    }
    result = redact(payload)
    assert result["outer"]["headers"]["Authorization"] == REDACTED
    assert result["outer"]["count"] == 3
    assert result["items"][0]["token"] == REDACTED
    assert result["items"][1]["ok"] is True


def test_deeply_nested_structures_are_truncated() -> None:
    """Защита от бесконечной вложенности: журнал не должен зависать."""
    payload: dict[str, object] = {"level": "end"}
    for _ in range(12):
        payload = {"level": payload}
    assert "truncated" in json.dumps(redact(payload))


def _format(record: logging.LogRecord) -> dict[str, object]:
    formatter = JsonFormatter(service="medsignal", environment="local")
    RedactingFilter().filter(record)
    return json.loads(formatter.format(record))


def _make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="сообщение",
        args=(),
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


def test_formatter_emits_valid_json_with_expected_fields() -> None:
    payload = _format(_make_record(hospital_id="H-1"))
    assert payload["level"] == "INFO"
    assert payload["message"] == "сообщение"
    assert payload["service"] == "medsignal"
    assert payload["hospital_id"] == "H-1"


def test_formatter_includes_request_id_when_known() -> None:
    with request_id_scope("abcdef123456"):
        payload = _format(_make_record())
    assert payload["request_id"] == "abcdef123456"


def test_formatter_omits_request_id_when_unknown() -> None:
    assert "request_id" not in _format(_make_record())


def test_formatter_redacts_sensitive_extra_fields() -> None:
    payload = _format(_make_record(authorization="Bearer secret", token="abc"))
    assert payload["authorization"] == REDACTED
    assert payload["token"] == REDACTED
    assert "secret" not in json.dumps(payload)

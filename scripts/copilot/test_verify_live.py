"""No-network checks for the sanitized live verifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.copilot.verify_live import _project, _validate_response


def _response() -> dict:
    return {
        "signal_id": "11111111-1111-4111-8111-111111111111",
        "signal_version": 1,
        "title": "Пояснение сигнала",
        "explanation": (
            "Наблюдаемое изменение в синтетическом примере "
            "требует проверки сотрудником."
        ),
        "fact_ids": ["F1"],
        "facts": [
            {
                "id": "F1",
                "metric_code": "queue_size",
                "label": "Размер очереди",
                "value": 21.0,
                "unit": "percent_change",
                "direction": "INCREASE",
                "period_start": None,
                "period_end": None,
                "source": "signal_explanation",
            }
        ],
        "data_current": False,
        "data_watermark_at": None,
        "limitations": [
            "Синтетические данные.",
            "Не доказана первопричина.",
            "Исторические данные не являются текущей очередью.",
        ],
        "generated_at": "2026-09-26T12:00:00Z",
        "request_id": "test-request",
        "llm_generated": True,
        "provider": "openai",
        "model": "gpt-4.1-mini-2025-04-14",
    }


def _detail(body: dict) -> dict:
    return {
        "id": body["signal_id"],
        "version": 1,
        "explanation": {
            "factors": [
                {"metric_code": "queue_size", "change_pct": 21.0, "direction": "INCREASE"}
            ],
            "input_period_start": None,
            "input_period_end": None,
        },
    }


def test_sanitized_verifier_accepts_contract_without_unknown_date_fill() -> None:
    body = _response()
    assert all(_validate_response(body, _detail(body)).values())


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        ("fact_ids", ["UNKNOWN"], "fact_ids"),
        ("explanation", "Очередь выросла на 21 процент.", "no_unchecked_text_claims"),
        ("explanation", "Изменение вызвано нехваткой коек.", "no_unchecked_text_claims"),
        ("data_current", True, "synthetic_historical_limitations"),
        ("llm_generated", False, "provenance"),
        ("evaluation_period_start", "2026-09-26", "unknown_dates_preserved"),
    ],
)
def test_sanitized_verifier_rejects_unsupported_claims(
    field: str, value: object, check: str
) -> None:
    body = _response()
    body[field] = value
    assert _validate_response(body, _detail(body))[check] is False


def test_verifier_rejects_fact_value_changed_after_backend() -> None:
    body = _response()
    body["facts"][0]["value"] = 99.0
    assert _validate_response(body, _detail(body))["facts_match_server"] is False


def test_project_rejects_non_loopback_or_non_acceptance(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"project":"production","origin":"https://example.org"}', encoding="utf-8"
    )
    (tmp_path / "realm.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="loopback phase8"):
        _project(tmp_path)

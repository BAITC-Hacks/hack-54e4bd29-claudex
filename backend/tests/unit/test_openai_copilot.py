"""Адаптер отправляет только synthetic facts в Responses API."""

from __future__ import annotations

import json
import logging
import re

import httpx
import pytest

from app.adapters.openai_copilot import OpenAICopilotProvider
from app.core.exceptions import AppError


def _provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICopilotProvider(
        api_key="fake-local-key",
        model="gpt-4.1-mini-2025-04-14",
        timeout_seconds=2,
        max_output_tokens=1200,
        client=client,
    )


def _response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 45, "output_tokens": 78},
        },
    )


def test_responses_api_structured_store_false_and_no_tools() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["model"] == "gpt-4.1-mini-2025-04-14"
        assert body["store"] is False
        assert body["tools"] == []
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["max_output_tokens"] == 1200
        instructions = body["instructions"]
        assert "Пример корректного JSON" in instructions
        assert '"fact_ids":["F1"]' in instructions
        assert "не помещай F1" in instructions
        assert "без чисел" in instructions
        example = instructions.split("Пример корректного JSON: ", 1)[1].split("}. ", 1)[0]
        parsed_example = json.loads(example + "}")
        assert re.search(r"\d", parsed_example["explanation"]) is None
        assert parsed_example["fact_ids"] == ["F1"]
        return _response(
            '{"explanation":"Синтетическое наблюдение с ограничениями.",'
            '"fact_ids":["F1"]}'
        )

    result = _provider(handler).explain({"rule": "QUEUE_GROWTH", "facts": []})
    assert result["fact_ids"] == ["F1"]
    assert len(seen) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"error": "private details"}),
        httpx.Response(429, json={"error": "private details"}),
    ],
)
def test_provider_failure_has_safe_error(response: httpx.Response) -> None:
    calls = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(True)
        return response

    provider = _provider(handler)
    with pytest.raises(AppError) as exc:
        provider.explain({"facts": []})
    assert exc.value.code == "COPILOT_PROVIDER_UNAVAILABLE"
    assert "private" not in str(exc.value)
    assert calls == [True]


def test_provider_timeout_has_safe_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private upstream diagnostics")

    with pytest.raises(AppError) as exc:
        _provider(handler).explain({"facts": []})
    assert exc.value.code == "COPILOT_PROVIDER_TIMEOUT"
    assert "private" not in str(exc.value)


@pytest.mark.parametrize(
    "response",
    [
        _response("not-json"),
        httpx.Response(200, json={"status": "incomplete", "output": []}),
        httpx.Response(200, json={"status": "completed", "output": []}),
    ],
)
def test_invalid_structured_output_rejected(response: httpx.Response) -> None:
    with pytest.raises(AppError) as exc:
        _provider(lambda _request: response).explain({"facts": []})
    assert exc.value.code == "COPILOT_INVALID_RESPONSE"


def test_missing_key_does_not_call_api() -> None:
    called = []

    def handler(_request: httpx.Request) -> httpx.Response:
        called.append(True)
        return _response("{}")

    provider = _provider(handler)
    provider._api_key = ""
    with pytest.raises(AppError) as exc:
        provider.explain({"facts": []})
    assert exc.value.code == "COPILOT_PROVIDER_UNAVAILABLE"
    assert called == []


def test_secret_and_provider_payload_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        response = _response(
            '{"explanation":"Синтетический факт требует проверки сотрудником.",'
            '"fact_ids":["F1"]}'
        )
        body = response.json()
        body["usage"]["input_tokens"] = "fake-local-key"
        return httpx.Response(200, json=body)

    with caplog.at_level(logging.INFO):
        _provider(handler).explain({"facts": [{"value": 21.0}]})
    assert "fake-local-key" not in caplog.text
    assert "21.0" not in caplog.text
    assert "Синтетический факт" not in caplog.text
    assert any(
        record.__dict__.get("output_usage_count") == 78 for record in caplog.records
    )

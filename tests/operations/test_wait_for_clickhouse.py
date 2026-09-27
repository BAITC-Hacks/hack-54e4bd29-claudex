"""Behavioral tests for the acceptance-only ClickHouse network gate."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from scripts.operations import wait_for_clickhouse


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.status = status
        self._body = BytesIO(body)
        self.read_sizes: list[int] = []

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._body.read(size)


@pytest.fixture
def config() -> wait_for_clickhouse.ReadinessConfig:
    return wait_for_clickhouse.ReadinessConfig(
        host="clickhouse",
        port=8123,
        username="medsignal",
        password="synthetic-private-value",
        request_timeout_seconds=0.25,
        deadline_seconds=1.0,
        retry_interval_seconds=0.4,
    )


def test_transient_network_failure_retries_then_requires_expected_select_result(
    config: wait_for_clickhouse.ReadinessConfig,
) -> None:
    clock = FakeClock()
    response = FakeResponse(b"1\n")
    calls = 0
    lines: list[str] = []

    def open_url(request: object, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        assert timeout <= config.request_timeout_seconds
        assert request.full_url == "http://clickhouse:8123/"
        assert request.data == b"SELECT 1"
        assert config.password not in request.full_url
        if calls == 1:
            raise URLError(ConnectionRefusedError("synthetic refusal"))
        return response

    exit_code = wait_for_clickhouse.wait_until_ready(
        config,
        open_url=open_url,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        emit=lines.append,
    )

    assert exit_code == 0
    assert calls == 2
    assert response.read_sizes == [wait_for_clickhouse.MAX_RESPONSE_BYTES + 1]
    assert any("category=NETWORK_TRANSIENT" in line for line in lines)
    assert any("category=READY" in line and "http_status=200" in line for line in lines)
    assert config.password not in "\n".join(lines)


def test_transient_network_failure_stops_at_overall_deadline(
    config: wait_for_clickhouse.ReadinessConfig,
) -> None:
    clock = FakeClock()
    lines: list[str] = []

    def unavailable(_request: object, *, timeout: float) -> FakeResponse:
        clock.now += timeout
        raise URLError(TimeoutError("synthetic timeout"))

    exit_code = wait_for_clickhouse.wait_until_ready(
        replace(config, deadline_seconds=0.7, retry_interval_seconds=0.2),
        open_url=unavailable,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        emit=lines.append,
    )

    assert exit_code != 0
    assert lines[-1].startswith("CLICKHOUSE_READY_FAIL")
    assert "category=DEADLINE_EXCEEDED" in lines[-1]
    assert "attempts=" in lines[-1]


@pytest.mark.parametrize("status", [401, 403, 500])
def test_http_auth_or_sql_error_fails_immediately_without_retry(
    status: int,
    config: wait_for_clickhouse.ReadinessConfig,
) -> None:
    clock = FakeClock()
    lines: list[str] = []
    calls = 0

    def rejected(request: object, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, status, "synthetic", {}, None)

    exit_code = wait_for_clickhouse.wait_until_ready(
        config,
        open_url=rejected,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        emit=lines.append,
    )

    assert exit_code != 0
    assert calls == 1
    assert lines[-1].startswith("CLICKHOUSE_READY_FAIL")
    assert f"http_status={status}" in lines[-1]
    assert "category=HTTP_ERROR" in lines[-1]
    assert config.password not in "\n".join(lines)


def test_http_200_with_unexpected_body_fails_without_retry(
    config: wait_for_clickhouse.ReadinessConfig,
) -> None:
    clock = FakeClock()
    lines: list[str] = []
    calls = 0

    def wrong_result(_request: object, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(b"0\n")

    exit_code = wait_for_clickhouse.wait_until_ready(
        config,
        open_url=wrong_result,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        emit=lines.append,
    )

    assert exit_code != 0
    assert calls == 1
    assert "category=UNEXPECTED_RESPONSE" in lines[-1]
    assert "http_status=200" in lines[-1]

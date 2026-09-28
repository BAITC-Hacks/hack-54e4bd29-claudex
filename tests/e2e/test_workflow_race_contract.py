"""The live acceptance harness must not label failed races as successful."""

from threading import Lock

import httpx
import pytest

from scripts.phase8_e2e import acknowledge_race


def test_acknowledgement_race_checks_one_success_and_one_conflict():
    lock = Lock()
    seen = []

    def respond(request):
        with lock:
            seen.append(request.headers["Authorization"])
            code = 200 if len(seen) == 1 else 409
        return httpx.Response(code, json={"id": "synthetic", "version": 2})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = acknowledge_race(
            client,
            "http://example.test/api/v1",
            ("synthetic-a", "synthetic-b"),
            {"id": "synthetic", "version": 1},
        )
    assert result["version"] == 2
    assert set(seen) == {"Bearer synthetic-a", "Bearer synthetic-b"}


def test_two_successful_writes_are_an_acceptance_failure():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"id": "synthetic"})
            )
        ) as client,
        pytest.raises(RuntimeError, match="one success and one conflict"),
    ):
        acknowledge_race(
            client,
            "http://example.test/api/v1",
            ("synthetic-a", "synthetic-b"),
            {"id": "synthetic", "version": 1},
        )

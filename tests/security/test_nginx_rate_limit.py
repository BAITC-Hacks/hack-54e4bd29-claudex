"""Exercise the real edge proxy's throttling contract with a disposable container."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[2]
NGINX_IMAGE = (
    "nginx:1.30.5-alpine@sha256:"
    "f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d"
)


def _docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True, timeout=30
    )
    return result.stdout.strip()


def _request(url: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(url, headers={"X-Request-ID": "p1-rate-contract"})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker required")
def test_nginx_rate_limit_has_429_json_retry_and_request_id() -> None:
    """Missing Retry-After, request ID, or JSON must break this test."""
    name = f"medsignal-p1-rate-{uuid.uuid4().hex[:12]}"
    try:
        _docker(
            "run", "--detach", "--rm", "--name", name,
            "--add-host", "backend:127.0.0.1",
            "--add-host", "frontend:127.0.0.1",
            "--add-host", "keycloak:127.0.0.1",
            "--publish", "127.0.0.1::80",
            "--volume", f"{ROOT / 'infrastructure/nginx/nginx.conf'}:/etc/nginx/nginx.conf:ro",
            "--volume", f"{ROOT / 'infrastructure/nginx/conf.d'}:/etc/nginx/conf.d:ro",
            NGINX_IMAGE,
        )
        port = _docker("port", name, "80/tcp").rsplit(":", 1)[-1]
        base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                if _request(f"{base}/healthz")[0] == 200:
                    break
            except URLError:
                time.sleep(0.1)
        else:
            raise AssertionError("Disposable Nginx did not become ready")

        with ThreadPoolExecutor(max_workers=48) as pool:
            responses = list(
                pool.map(lambda _: _request(f"{base}/api/v1/health"), range(120))
            )
        limited = [response for response in responses if response[0] == 429]
        assert limited, "Burst should trigger edge throttling"
        status, headers, body = limited[0]
        assert status == 429
        assert headers.get("Retry-After") == "1"
        assert headers.get("X-Request-ID") == "p1-rate-contract"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("Content-Type", "").startswith("application/json")
        assert json.loads(body) == {
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Превышен лимит запросов",
                "details": {},
                "request_id": "p1-rate-contract",
            }
        }
        # API and analytics spend separate per-IP budgets. A throttled API
        # caller must still reach the analytics upstream (stub returns 502).
        assert _request(f"{base}/api/v1/analytics/overview")[0] == 502

        with ThreadPoolExecutor(max_workers=32) as pool:
            auth_responses = list(
                pool.map(lambda _: _request(f"{base}/auth/realms/medsignal"), range(80))
            )
        assert any(status == 429 for status, _, _ in auth_responses)
        # Import has its own limit zone instead of exhausting auth's budget.
        assert _request(f"{base}/api/v1/data/import")[0] == 502
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True, text=True, check=False, timeout=30,
        )

"""Unauthenticated research pilot cannot be reached through product routes."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_pilot_has_only_loopback_frontend_and_no_public_api_port() -> None:
    pilot = yaml.safe_load(
        (ROOT / "docker-compose.pilot.yml").read_text(encoding="utf-8")
    )
    services = pilot["services"]

    assert "ports" not in services["pilot-api"]
    assert services["frontend"]["ports"] == ["127.0.0.1:8088:3000"]
    assert pilot["name"] == "medsignal-pilot"


def test_product_edge_and_fastapi_exclude_pilot_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_SECRET", "synthetic-test-local_dev_only")
    from app.api.v1.router import api_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    edge = (ROOT / "infrastructure/nginx/conf.d/default.conf").read_text(encoding="utf-8")
    assert "pilot-api" not in edge
    assert "proxy_pass http://medsignal_backend" in edge

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    response = TestClient(app).get("/api/pilot/health")
    assert response.status_code == 404

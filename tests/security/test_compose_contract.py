"""Static deployment contracts that must not depend on a running Docker daemon."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docker-compose.yml"
PRODUCTION = ROOT / "docker-compose.production.yml"


def _base() -> dict[str, object]:
    return yaml.safe_load(BASE.read_text(encoding="utf-8"))


def test_compose_does_not_pin_container_names() -> None:
    services = _base()["services"]
    assert isinstance(services, dict)
    assert all("container_name" not in service for service in services.values())


def test_only_nginx_publishes_host_ports() -> None:
    services = _base()["services"]
    published = {name for name, service in services.items() if service.get("ports")}
    assert published == {"nginx"}


def test_clickhouse_migrations_are_a_startup_dependency() -> None:
    services = _base()["services"]
    migration = services["clickhouse-migrate"]
    assert migration["restart"] == "no"
    assert migration["depends_on"]["clickhouse"]["condition"] == "service_healthy"
    assert "app.cli.clickhouse" in " ".join(migration["entrypoint"])

    for dependent in ("backend", "worker", "pipeline", "ml-runner"):
        assert (
            services[dependent]["depends_on"]["clickhouse-migrate"]["condition"]
            == "service_completed_successfully"
        )


def test_production_overlay_uses_production_images_and_removes_dev_mounts() -> None:
    assert PRODUCTION.is_file()
    text = PRODUCTION.read_text(encoding="utf-8")
    for service in ("frontend", "backend", "worker", "migrate", "clickhouse-migrate"):
        assert f"  {service}:" in text
        assert "target: production" in text[text.index(f"  {service}:") :]

    assert "!reset []" in text
    assert "start-dev" not in text
    assert "realm-medsignal-dev.json" not in text


def test_base_compose_remains_the_local_demo_workflow() -> None:
    services = _base()["services"]
    assert services["backend"]["build"]["target"] == "development"
    assert services["frontend"]["build"]["target"] == "development"
    assert "--reload" in services["backend"]["command"]
    assert "start-dev" in services["keycloak"]["command"]

"""MLflow must admit its private Compose hostname without widening access."""

from pathlib import Path

import yaml


def test_mlflow_allows_only_expected_internal_hosts():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    mlflow = compose["services"]["mlflow"]
    command = mlflow["command"]
    allowed = [part for part in command if part.startswith("--allowed-hosts=")]
    assert allowed == [
        "--allowed-hosts=mlflow:5000,mlflow,localhost:5000,localhost,"
        "127.0.0.1:5000,127.0.0.1"
    ]
    assert "--disable-security-middleware" not in command


def test_mlflow_does_not_publish_host_ports():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "ports" not in compose["services"]["mlflow"]

from __future__ import annotations

from pathlib import Path


def test_security_patched_runtime_versions_are_pinned() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    nginx_dockerfile = Path("infrastructure/nginx/Dockerfile").read_text(encoding="utf-8")
    ml_requirements = Path("ml/requirements.txt").read_text(encoding="utf-8")
    mlflow_dockerfile = Path("infrastructure/docker/mlflow.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "medsignal-nginx:local" in compose
    assert "infrastructure/nginx" in compose
    assert "nginx:1.30.5-alpine@sha256:" in nginx_dockerfile
    assert "libexpat=2.8.5-r0" in nginx_dockerfile
    assert "mlflow==3.16.1" in ml_requirements
    assert "FROM python:3.12-slim" in mlflow_dockerfile
    assert "mlflow==3.16.1" in mlflow_dockerfile
    assert "GitPython==3.1.59" in mlflow_dockerfile
    assert "cryptography==50.0.0" in mlflow_dockerfile


def test_backend_security_fixed_versions_are_pinned() -> None:
    requirements = Path("backend/requirements.txt").read_text(encoding="utf-8")

    assert "fastapi==0.141.*" in requirements
    assert "starlette==1.3.1" in requirements
    assert "PyJWT[crypto]==2.13.0" in requirements
    assert "cryptography==50.0.0" in requirements


def test_frontend_runtime_removes_unused_npm_package_manager() -> None:
    dockerfile = Path("frontend/Dockerfile").read_text(encoding="utf-8")

    assert "/usr/local/lib/node_modules/npm" in dockerfile

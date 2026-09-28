#!/usr/bin/env python3
"""Проверка того, что наружу публикуется только обратный прокси.

Требование SECURITY.md, раздел 2: PostgreSQL, ClickHouse, Redis, MinIO
и MLflow не имеют портов на хосте. Проверка выполняется по разобранной
конфигурации Docker Compose, а не по исходному файлу: наложения и
подстановка переменных способны добавить публикацию незаметно.

Запуск:
    docker compose config --format json | python scripts/check-published-ports.py
    docker compose -f docker-compose.yml -f docker-compose.dev-ports.yml \\
        config --format json | python scripts/check-published-ports.py --allow-loopback

Код выхода 1 означает нарушение.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Единственный сервис, которому разрешено слушать на всех интерфейсах.
PUBLIC_SERVICE = "nginx"

# Сервисы, публикация которых наружу недопустима ни при каких условиях.
MUST_STAY_PRIVATE = frozenset({"postgres", "clickhouse", "redis", "minio", "mlflow"})

LOOPBACK = {"127.0.0.1", "::1"}


def iter_published(config: dict[str, Any]):
    for name, spec in sorted((config.get("services") or {}).items()):
        for port in spec.get("ports") or []:
            yield (
                name,
                port.get("host_ip") or "0.0.0.0",  # noqa: S104 -- rendered default
                port.get("published"),
                port.get("target"),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-loopback",
        action="store_true",
        help="разрешить публикацию на 127.0.0.1 (наложение для диагностики)",
    )
    args = parser.parse_args()

    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Не удалось разобрать конфигурацию compose: {exc}", file=sys.stderr)
        return 2

    violations: list[str] = []
    published_any = False

    for service, host_ip, published, target in iter_published(config):
        published_any = True
        location = f"{host_ip}:{published}->{target}"

        if service == PUBLIC_SERVICE:
            print(f"  {service:<12} {location}  публичный вход, допустимо")
            continue

        if args.allow_loopback and host_ip in LOOPBACK:
            print(f"  {service:<12} {location}  только петля, допустимо")
            continue

        reason = (
            "хранилище не может публиковаться наружу"
            if service in MUST_STAY_PRIVATE
            else "публиковать наружу разрешено только обратному прокси"
        )
        print(f"  {service:<12} {location}  НАРУШЕНИЕ: {reason}")
        violations.append(f"{service} ({location})")

    if not published_any:
        print("  ни один сервис не публикует портов")

    if violations:
        print(f"\nНедопустимая публикация портов: {', '.join(violations)}")
        return 1

    print("\nПубликация портов соответствует требованию")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

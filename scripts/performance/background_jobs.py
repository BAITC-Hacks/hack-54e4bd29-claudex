"""Build reproducible timing evidence for Phase 8 background operations.

The tool records aggregate timing only. It never reads or logs source rows,
tokens, identifiers or task payloads.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = frozenset({"COMPLETED", "FAILED", "SKIPPED"})
ALLOWED_SOURCES = frozenset({"wall_clock", "persistent_timestamps"})


def build_measurement(
    job: str,
    status: str,
    duration_seconds: float,
    measurement_source: str,
    dataset_size: dict[str, int],
) -> dict[str, Any]:
    if not job.strip():
        raise ValueError("job must not be empty")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    if measurement_source not in ALLOWED_SOURCES:
        raise ValueError(f"unsupported measurement source: {measurement_source}")
    if duration_seconds < 0:
        raise ValueError("duration must be non-negative")
    if any(value < 0 for value in dataset_size.values()):
        raise ValueError("dataset sizes must be non-negative")
    return {
        "job": job,
        "status": status,
        "duration_seconds": round(duration_seconds, 3),
        "measurement_source": measurement_source,
        "dataset_size": dict(sorted(dataset_size.items())),
    }


def build_report(
    measurements: list[dict[str, Any]], *, generated_at: str | None = None
) -> dict[str, Any]:
    return {
        "generated_at": generated_at
        or datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "measurements": measurements,
    }


def _parse_measurement(raw: str, dataset_size: dict[str, int]) -> dict[str, Any]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("measurement must be JOB,STATUS,DURATION_SECONDS,SOURCE")
    job, status, duration, source = parts
    return build_measurement(job, status, float(duration), source, dataset_size)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create aggregate background-job timing evidence"
    )
    parser.add_argument(
        "--measurement",
        action="append",
        required=True,
        help="JOB,STATUS,DURATION_SECONDS,SOURCE",
    )
    parser.add_argument("--dataset-size", type=json.loads, default={})
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        measurements = [
            _parse_measurement(item, args.dataset_size) for item in args.measurement
        ]
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))
    report = build_report(measurements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

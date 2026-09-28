"""Measure the aggregate organizations repository against published imports.

The script prints only timings and aggregate counts, never source keys.
Run inside a backend container with its normal private-network environment.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime

from app.database.clickhouse import get_client
from app.database.postgres import get_session_factory
from app.repositories.analytics_metadata import SqlAlchemyAnalyticsMetadataRepository
from app.repositories.clickhouse_analytics import ClickHouseAnalyticsRepository
from app.shared.analytics_contracts import AnalyticsFilter
from app.shared.analytics_data import QueryScope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error("iterations must be between 1 and 100")

    metadata = SqlAlchemyAnalyticsMetadataRepository(get_session_factory())
    watermark = metadata.latest_completed_imports()
    scope = QueryScope(
        canonical_hospital_ids=(),
        all_canonical=True,
        include_unmapped=True,
        mapping_version=watermark.mapping_version,
        published_import_ids=watermark.import_ids,
    )
    filters = AnalyticsFilter(
        date_from=datetime(2025, 1, 1, tzinfo=UTC),
        date_to=datetime(2025, 3, 31, 23, 59, 59, 999000, tzinfo=UTC),
    )
    repository = ClickHouseAnalyticsRepository(get_client())
    samples: list[float] = []
    row_count = 0
    total = 0
    for _ in range(args.iterations):
        start = time.perf_counter()
        rows, total = repository.organizations(filters, scope, limit=20, offset=0)
        samples.append(round((time.perf_counter() - start) * 1000, 2))
        row_count = len(rows)
    print(
        json.dumps(
            {
                "iterations": args.iterations,
                "latency_ms": samples,
                "median_ms": round(statistics.median(samples), 2),
                "page_rows": row_count,
                "total_organizations": total,
                "published_imports": len(watermark.import_ids),
                "scope": "global",
                "date_from": filters.date_from.date().isoformat(),
                "date_to": filters.date_to.date().isoformat(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

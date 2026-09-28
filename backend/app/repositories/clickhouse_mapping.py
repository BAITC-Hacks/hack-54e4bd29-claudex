"""Idempotent candidate insertion under the PG mapping lock; verify before activation."""

from __future__ import annotations

from typing import Any, Protocol

from app.core.exceptions import ConflictError
from app.repositories.clickhouse_analytics import QueryResult
from app.shared.mapping import MappingSnapshot


class ProjectionClient(Protocol):
    def query(
        self, query: str, parameters: dict[str, object] | None = None
    ) -> QueryResult: ...
    def insert(
        self, table: str, data: list[tuple[str, ...]], column_names: list[str]
    ) -> Any: ...


class ClickHouseMappingRepository:
    def __init__(self, client: ProjectionClient) -> None:
        self._client = client

    def _rows(self, version: str) -> tuple[tuple[str, str, str, str], ...]:
        result = self._client.query(
            """SELECT kind, identity_space, source_key, toString(canonical_id)
            FROM mapping_projection WHERE version = {version:String}
            ORDER BY kind, identity_space, source_key""",
            parameters={"version": version},
        )
        return tuple(
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in result.result_rows
        )

    def publish(self, snapshot: MappingSnapshot) -> None:
        expected = snapshot.rows()
        validated = MappingSnapshot.from_rows(snapshot.version, expected)
        if validated.digest != snapshot.digest:
            raise ConflictError("MAPPING_DIGEST_MISMATCH")
        existing = self._rows(snapshot.version)
        if len(existing) != len(set(existing)) or not set(existing).issubset(
            set(expected)
        ):
            raise ConflictError("MAPPING_CANDIDATE_CORRUPT")
        missing = sorted(set(expected) - set(existing))
        if missing:
            self._client.insert(
                "mapping_projection",
                [(snapshot.version, *row) for row in missing],
                column_names=[
                    "version",
                    "kind",
                    "identity_space",
                    "source_key",
                    "canonical_id",
                ],
            )
        actual = self._rows(snapshot.version)
        if (
            len(actual) != len(expected)
            or MappingSnapshot.from_rows(snapshot.version, actual).digest
            != snapshot.digest
        ):
            raise ConflictError("MAPPING_PROJECTION_UNVERIFIED")

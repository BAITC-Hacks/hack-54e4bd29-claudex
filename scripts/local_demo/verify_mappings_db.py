"""Read-only exact check of the active local synthetic mapping projection.

Pipe this file to ``docker compose exec -T backend python -``. It prints only
the count and PASS status, never IDs or connection details.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def assert_exact_mappings(
    specs: Sequence[tuple[str, str, str, str]],
    targets: Mapping[str, str],
    actual: Sequence[tuple[str, str, str, str]],
) -> None:
    """Require every source alias and exact canonical UUID, with no extras."""
    try:
        expected = tuple(sorted(
            (kind, space, key, str(targets[target_code]))
            for kind, space, key, target_code in specs
        ))
    except KeyError as exc:
        raise AssertionError("Published mapping snapshot target missing") from exc
    if tuple(actual) != expected:
        raise AssertionError("Published mapping snapshot differs from local profile")


def main() -> None:
    from app.database.clickhouse import get_client
    from app.database.postgres import session_scope
    from app.models.directory import Hospital, Region
    from app.models.mapping import MappingState
    from seeds.local_demo_mappings import mapping_specs
    from seeds.local_demo_seed import load_profile
    from sqlalchemy import select

    specs = mapping_specs(load_profile())
    with session_scope() as session:
        state = session.get(MappingState, 1)
        if (
            state is None
            or not state.active_version
            or state.active_generation != state.generation
        ):
            raise AssertionError("Published mapping snapshot is not active")
        version = state.active_version
        targets = {
            **{row.code: str(row.id) for row in session.scalars(select(Region))},
            **{row.code: str(row.id) for row in session.scalars(select(Hospital))},
        }
    result = get_client().query(
        """SELECT kind, identity_space, source_key, toString(canonical_id)
        FROM mapping_projection WHERE version = {version:String}
        ORDER BY kind, identity_space, source_key""",
        parameters={"version": version},
    )
    actual = tuple(tuple(str(value) for value in row) for row in result.result_rows)
    assert_exact_mappings(specs, targets, actual)
    print(json.dumps({"mapping": "PASS", "aliases": len(actual)}))


if __name__ == "__main__":
    main()

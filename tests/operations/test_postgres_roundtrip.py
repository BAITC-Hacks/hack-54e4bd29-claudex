"""Opt-in real PostgreSQL roundtrip; requires a task-owned Compose project."""

from __future__ import annotations

import os
import shlex
import uuid

import pytest

from scripts.operations import common


def test_postgres_dump_roundtrip_preserves_checks_and_detects_constraint_drift():
    project = os.environ.get("OPERATIONS_TEST_PROJECT")
    if not project:
        pytest.skip("set OPERATIONS_TEST_PROJECT and isolated Compose configuration")
    common.require_phase8_namespace(project)
    prefix = f"phase8_ops_{uuid.uuid4().hex}"
    source, restored = f"{prefix}_source", f"{prefix}_restored"
    created = []

    def psql(database, sql):
        command = (
            'psql -X -qAt -U "$POSTGRES_USER" -d '
            + shlex.quote(database)
            + " -v ON_ERROR_STOP=1"
        )
        return common.compose(
            project,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            command,
            input_bytes=sql.encode(),
        )

    try:
        for database in (source, restored):
            psql("postgres", f'CREATE DATABASE "{database}"')
            created.append(database)
        psql(
            source,
            """
            CREATE TABLE synthetic_operations (
                id integer PRIMARY KEY,
                status varchar(20) NOT NULL,
                CONSTRAINT synthetic_status CHECK (
                    status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')
                )
            );
            INSERT INTO synthetic_operations VALUES (1, 'PENDING'), (2, 'RUNNING');
        """,
        )
        expected = common.postgres_inventory(project, source)
        dump = common.compose(
            project,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            f'pg_dump -U "$POSTGRES_USER" -d {source} --format=custom',
        )
        common.compose(
            project,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            f'pg_restore -U "$POSTGRES_USER" -d {restored} --exit-on-error',
            input_bytes=dump,
        )
        actual = common.postgres_inventory(project, restored)
        assert actual["tables"] == {"synthetic_operations": 2}
        assert len(actual["constraints"]) == 2
        common.verify_postgres_inventory(expected, actual)

        # Equivalent cast syntax must pass, but a changed allowed value must fail.
        psql(
            restored,
            """
            ALTER TABLE synthetic_operations DROP CONSTRAINT synthetic_status;
            ALTER TABLE synthetic_operations ADD CONSTRAINT synthetic_status
                CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'EXTRA'));
        """,
        )
        with pytest.raises(RuntimeError, match="constraint/revision mismatch"):
            common.verify_postgres_inventory(
                expected, common.postgres_inventory(project, restored)
            )
    finally:
        for database in reversed(created):
            assert database.startswith(prefix)
            psql("postgres", f'DROP DATABASE "{database}"')

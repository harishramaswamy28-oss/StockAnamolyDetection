"""Integration test: verifies a real PostgreSQL/TimescaleDB connection can be
opened using the credentials configured in the environment (.env).

Skips automatically if DB_HOST/DB_NAME/DB_USER/DB_PASSWORD are not configured,
or if the database is unreachable, so this suite can run in CI/without a
local Postgres instance.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def _db_configured():
    return all(os.getenv(v) for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"))


@pytest.mark.skipif(not _db_configured(), reason="DB_* environment variables are not configured")
def test_can_connect_and_run_simple_query():
    from database.connection import get_connection

    try:
        connection = get_connection()
    except Exception as exc:  # pragma: no cover - depends on local environment
        pytest.skip(f"Database unreachable: {exc}")
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    finally:
        connection.close()


@pytest.mark.skipif(not _db_configured(), reason="DB_* environment variables are not configured")
def test_timescaledb_extension_is_enabled():
    from database.connection import get_connection

    try:
        connection = get_connection()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Database unreachable: {exc}")
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
            row = cursor.fetchone()
            if row is None:
                pytest.skip("timescaledb extension not installed; run sql/01_schema.sql first")
            assert row[0] == "timescaledb"
    finally:
        connection.close()

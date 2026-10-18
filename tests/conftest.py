"""Shared pytest fixtures and lightweight database test doubles.

Unit tests in this project never talk to a real PostgreSQL instance. Instead,
modules that call ``database.connection.get_connection()`` are monkeypatched
to return a ``FakeConnection`` wired up with a scripted sequence of
``fetchone``/``fetchall`` results. This lets the SQL-orchestration logic in
``analysis``, ``alerts``, ``realtime``, and ``api`` be exercised exactly as it
runs in production, without requiring a live database.

Tests that genuinely require a live PostgreSQL/TimescaleDB instance and/or
real Alpaca API credentials are marked with ``@pytest.mark.integration`` and
skip automatically when the required environment variables are not present
(see each integration test module for its specific precondition).
"""
import os

import pytest
from dotenv import load_dotenv


# Load project credentials before integration-test skip markers inspect the
# environment. Otherwise a correctly configured local .env is invisible until
# after those markers have already decided to skip the tests.
load_dotenv()
# TestClient enters FastAPI lifespan in current Starlette versions. Keep its
# background market workers disabled so API unit tests remain deterministic.
os.environ.setdefault("AUTO_MONITORING_ENABLED", "false")


class FakeCursor:
    """A minimal stand-in for a psycopg cursor.

    ``steps`` is a list of dicts describing what each successive
    ``cursor.execute(...)`` call should make available afterwards, e.g.:

        steps=[
            {"fetchone": (1,)},          # first execute() -> fetchone() returns (1,)
            {"fetchall": [(1, "a")]},    # second execute() -> fetchall() returns rows
            {},                            # third execute() -> no fetch performed
        ]

    Every ``execute()`` call is recorded in ``self.queries`` (SQL text + params)
    so tests can assert on what was actually sent to the database when needed.
    """

    def __init__(self, steps=None):
        self.steps = list(steps or [])
        self._pos = -1
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        self._pos += 1

    def _current(self):
        if self._pos < 0 or self._pos >= len(self.steps):
            return {}
        return self.steps[self._pos]

    def fetchone(self):
        return self._current().get("fetchone")

    def fetchall(self):
        return self._current().get("fetchall", [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    """A minimal stand-in for a psycopg connection backed by a FakeCursor."""

    def __init__(self, steps=None):
        self.cursor_obj = FakeCursor(steps)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


@pytest.fixture
def fake_connection():
    """Factory fixture: fake_connection(steps) -> FakeConnection."""
    def _make(steps=None):
        return FakeConnection(steps)
    return _make

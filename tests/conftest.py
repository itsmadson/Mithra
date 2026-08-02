"""Shared test database setup.

The suites drop and recreate every table they touch, so they must never run
against the development database — doing so destroys real jobs and leaves the
running app with missing tables. Everything here points at a separate database
that exists only for tests, created on demand.

Override with MITHRA_TEST_DATABASE_URL if you need somewhere else.
"""

import os

import psycopg
import pytest
from sqlalchemy import create_engine, text

DEV_DATABASE_URL = "postgresql+psycopg://mithra:mithra@localhost:5434/mithra"
TEST_DATABASE_URL = os.environ.get(
    "MITHRA_TEST_DATABASE_URL",
    "postgresql+psycopg://mithra:mithra@localhost:5434/mithra_test",
)

DB_URL = TEST_DATABASE_URL


def _database_name(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _admin_dsn(url: str) -> str:
    """The same server, the `postgres` database, as a plain psycopg DSN.

    Derived from the test URL rather than hardcoded: a hardcoded host, port and
    password only works on the machine it was written on, and elsewhere — CI, a
    colleague's laptop — it fails at connect time with an error about the wrong
    server entirely.
    """
    base = url.replace("postgresql+psycopg://", "postgresql://")
    return base.rsplit("/", 1)[0] + "/postgres"


def _ensure_database_exists() -> None:
    """CREATE DATABASE cannot run inside a transaction, hence raw psycopg."""
    name = _database_name(TEST_DATABASE_URL)
    admin_dsn = _admin_dsn(TEST_DATABASE_URL)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    if _database_name(TEST_DATABASE_URL) == _database_name(DEV_DATABASE_URL):
        raise RuntimeError(
            "refusing to run tests against the development database; "
            "set MITHRA_TEST_DATABASE_URL to a throwaway database"
        )
    _ensure_database_exists()
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    engine.dispose()

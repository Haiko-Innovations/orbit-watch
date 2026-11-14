from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from postgres import (
    SERVER_VARIABLE,
    Container,
    PostgresUnavailable,
    docker_available,
    drop_schema,
    new_schema,
    require_postgres,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def examples_dir() -> Path:
    return REPO_ROOT / "examples"


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[str | None]:
    """A PostgreSQL server for the session, or None (tests/postgres.py)."""
    given = os.environ.get(SERVER_VARIABLE)
    if given:
        yield given
        return
    try:
        import psycopg  # noqa: F401
    except ImportError:
        yield None
        return
    if not docker_available():
        yield None
        return
    try:
        container = Container()
    except PostgresUnavailable:
        yield None
        return
    try:
        yield container.conninfo
    finally:
        container.stop()


@pytest.fixture
def make_database(postgres_server: str | None) -> Iterator[Callable[[], str]]:
    """Makes new, empty databases (one schema each) for this test, and drops them after."""
    if postgres_server is None:
        require_postgres("no PostgreSQL server")
    made: list[str] = []

    def make() -> str:
        schema, conninfo = new_schema(postgres_server)
        made.append(schema)
        return conninfo

    yield make
    for schema in made:
        drop_schema(postgres_server, schema)


@pytest.fixture
def database(make_database: Callable[[], str]) -> str:
    """A new, empty database (one schema) for this test."""
    return make_database()

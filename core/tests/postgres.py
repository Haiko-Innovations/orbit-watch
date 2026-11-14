"""PostgreSQL for the tests and the local stack (phase 4, step 4.1; decision P4-04).

A server comes from ``ORBIT_WATCH_TEST_DATABASE_URL`` (a libpq URL of a database where
the tests may create and drop schemas), or else this module starts one in a container,
when Docker is there: PostgreSQL 18, as on Neon, from the official image pinned by
digest, listening on 127.0.0.1 only, with trust authentication and its data in memory.
It is a LOCAL TEST database with nothing worth protecting, and it is removed at the end.

Every test gets schemas of its own, so tests never see each other's data. Without a
server the tests that need one are skipped, unless ``ORBIT_WATCH_PG_TESTS=1`` (as in
CI), which makes a missing server a failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import pytest

# PostgreSQL 18.6, the newest minor release at least 14 days old on 2026-11-14.
POSTGRES_IMAGE = (
    "postgres:18.6@sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42"
)
SERVER_VARIABLE = "ORBIT_WATCH_TEST_DATABASE_URL"
REQUIRE_VARIABLE = "ORBIT_WATCH_PG_TESTS"


class PostgresUnavailable(RuntimeError):
    pass


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


class Container:
    """A throw-away PostgreSQL in Docker, on a free port of 127.0.0.1."""

    def __init__(self, name_prefix: str = "orbit-watch-test-db"):
        self.name = f"{name_prefix}-{uuid.uuid4().hex[:10]}"
        started = subprocess.run(
            [
                "docker", "run", "--rm", "--detach", "--name", self.name,
                "--publish", "127.0.0.1::5432",
                "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                "--tmpfs", "/var/lib/postgresql",
                POSTGRES_IMAGE,
                # A test database: speed over durability.
                "-c", "fsync=off", "-c", "synchronous_commit=off",
                "-c", "full_page_writes=off", "-c", "max_connections=300",
            ],
            capture_output=True,
            text=True,
        )  # fmt: skip
        if started.returncode != 0:
            raise PostgresUnavailable(f"docker run failed: {started.stderr.strip()}")
        try:
            port = (
                subprocess.run(
                    ["docker", "port", self.name, "5432/tcp"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                .stdout.split(":")[-1]
                .strip()
            )
            self.conninfo = f"postgresql://postgres@127.0.0.1:{port}/postgres"
            wait_until_ready(self.conninfo)
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "--force", self.name], capture_output=True)


def wait_until_ready(conninfo: str, timeout: float = 60.0) -> None:
    import psycopg

    deadline = time.monotonic() + timeout
    while True:
        try:
            with psycopg.connect(conninfo, connect_timeout=2) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise PostgresUnavailable("PostgreSQL did not start") from None
            time.sleep(0.3)


def new_schema(server: str, prefix: str = "test") -> tuple[str, str]:
    """A new, empty schema on ``server``: (its name, a connection string that uses it)."""
    import psycopg
    from psycopg.conninfo import make_conninfo

    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    # The schema's name is also the connections' application name, so that dropping the
    # schema can end any connection a test left open.
    return schema, make_conninfo(
        server, options=f"-c search_path={schema}", application_name=schema
    )


def drop_schema(server: str, schema: str) -> None:
    import psycopg

    with psycopg.connect(server, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = %s",
            (schema,),
        )
        connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def require_postgres(reason: str) -> None:
    if os.environ.get(REQUIRE_VARIABLE) == "1":
        pytest.fail(f"{REQUIRE_VARIABLE}=1 but {reason}")
    pytest.skip(f"{reason}; set {SERVER_VARIABLE}, or install Docker, to run these tests")

"""Storage: one PostgreSQL database (phase 1, step 1.5; PostgreSQL since phase 4, step 4.1).

Decision P4-04, which replaced P-02: PostgreSQL wherever the service keeps state, in
production, in the local stack and in the tests. Schema changes are numbered plain-SQL
migrations. Files (requests, observations, reports) are kept in the database by their
SHA-256; a hash identifies a file, it does not replace keeping it, so files are never
deleted.

A database is named by a libpq connection string or URL (``postgresql://…``). A
``search_path`` in its ``options`` selects a schema; the tests give every test one.

One service process per schema: the service holds a session advisory lock for as long as
it is open, and a second process gets ``StorageError("in_use")``. The service keeps its
working state in memory and writes every change through to the database inside one
transaction per operation. (Step 4.2 makes the service stateless.)

psycopg is imported only when a database is opened, so the command-line tools that keep
no state need neither psycopg nor a database.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from typing import Any

from orbit_watch.canonical import sha256_bytes

_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class StorageError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def available_migrations() -> list[tuple[int, str, str]]:
    """Packaged migrations as (version, name, SQL), in order."""
    folder = resources.files("orbit_watch.storage.migrations")
    found = []
    for entry in folder.iterdir():
        match = _MIGRATION_RE.match(entry.name)
        if match:
            found.append((int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8")))
    found.sort()
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(found) + 1)):
        raise StorageError("bad_migrations", f"migrations must be numbered 1..n, got {versions}")
    return found


@functools.lru_cache(maxsize=512)
def _placeholders(sql: str) -> str:
    """The SQL in psycopg's parameter style: ``?`` becomes ``%s`` (and a literal ``%``
    becomes ``%%``). Orbit Watch's SQL never has a literal question mark."""
    return sql.replace("%", "%%").replace("?", "%s")


class Database:
    """A PostgreSQL database (or one schema in it) for one Orbit Watch service."""

    def __init__(self, conninfo: str):
        import psycopg
        from psycopg.rows import dict_row

        try:
            # The connection may be used from a server's worker threads; callers
            # serialise access (the API holds one lock around every call).
            self.connection = psycopg.connect(conninfo, autocommit=True, row_factory=dict_row)
        except psycopg.Error as error:
            # libpq's message names the host and the user, never the password.
            raise StorageError("cannot_open", f"cannot open the database: {error}") from None
        self._depth = 0
        schema = self.query("SELECT current_schema() AS s")[0]["s"]
        if schema is None:
            self.close()
            raise StorageError("cannot_open", "the database's search_path names no schema")
        self.schema = schema
        # One service per schema, until step 4.2 makes the service stateless.
        held = self.query(
            "SELECT pg_try_advisory_lock(hashtext('orbit-watch/' || current_database() "
            "|| '/' || current_schema())) AS held"
        )[0]["held"]
        if not held:
            self.close()
            raise StorageError("in_use", f"the schema {schema} is used by another process")

    def close(self) -> None:
        if not self.connection.closed:
            self.connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def in_transaction(self) -> bool:
        return self._depth > 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One atomic unit of work. Nested calls join the outer transaction."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        self._depth = 1
        try:
            with self.connection.transaction():
                yield
        finally:
            self._depth = 0

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        if parameters:
            return self.connection.execute(_placeholders(sql), parameters)
        return self.connection.execute(sql)

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return self.execute(sql, parameters).fetchall()

    def schema_version(self) -> int:
        if not self._has_migrations_table():
            return 0
        row = self.query("SELECT MAX(version) AS v FROM schema_migrations")[0]
        return row["v"] or 0

    def tables(self) -> set[str]:
        """The tables of this schema."""
        rows = self.query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
        return {row["table_name"] for row in rows}

    def _has_migrations_table(self) -> bool:
        return "schema_migrations" in self.tables()

    def migrate(self) -> list[int]:
        """Apply the migrations that are missing. Returns the versions applied."""
        applied = []
        with self.transaction():
            self.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, sha256 TEXT NOT NULL)"
            )
            done = {row["version"]: row for row in self.query("SELECT * FROM schema_migrations")}
            for version, name, sql in available_migrations():
                digest = sha256_bytes(sql.encode("utf-8"))
                if version in done:
                    if done[version]["sha256"] != digest:
                        raise StorageError(
                            "migration_changed",
                            f"migration {version:04d}_{name} was changed after it was applied",
                        )
                    continue
                for statement in _statements(sql):
                    self.execute(statement)
                self.execute(
                    "INSERT INTO schema_migrations (version, name, sha256) VALUES (?, ?, ?)",
                    (version, name, digest),
                )
                applied.append(version)
        known = {v for v, _, _ in available_migrations()}
        newer = [v for v in done if v not in known]
        if newer:
            raise StorageError(
                "newer_schema", f"the database has migrations this version does not know: {newer}"
            )
        return applied


def _statements(sql: str) -> list[str]:
    """Split a migration into statements (no semicolons inside statements)."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


class FileStore:
    """Files kept in the database by their SHA-256, checked on every read. Never deleted."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _check(sha256: str) -> None:
        if not _SHA256_RE.fullmatch(sha256):
            raise StorageError("bad_hash", f"not a SHA-256: {sha256!r}")

    def put(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        self.db.execute(
            "INSERT INTO files (sha256, size, content) VALUES (?, ?, ?) "
            "ON CONFLICT (sha256) DO NOTHING",
            (digest, len(data), data),
        )
        return digest

    def get(self, sha256: str) -> bytes:
        self._check(sha256)
        rows = self.db.query("SELECT content FROM files WHERE sha256 = ?", (sha256,))
        if not rows:
            raise StorageError("missing_file", f"file {sha256} is missing")
        data = bytes(rows[0]["content"])
        if sha256_bytes(data) != sha256:
            raise StorageError("corrupt_file", f"file {sha256} does not match its hash")
        return data

    def __contains__(self, sha256: str) -> bool:
        self._check(sha256)
        return bool(self.db.query("SELECT 1 FROM files WHERE sha256 = ?", (sha256,)))


class Storage:
    """A service's database, files included."""

    def __init__(self, conninfo: str):
        self.db = Database(conninfo)
        try:
            self.db.migrate()
        except BaseException:
            self.db.close()
            raise
        self.files = FileStore(self.db)

    def close(self) -> None:
        self.db.close()

    def put_file(self, data: bytes) -> str:
        """Keep a file, in the caller's transaction."""
        return self.files.put(data)

    def has_file(self, sha256: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM files WHERE sha256 = ?", (sha256,)))


class StoredFiles:
    """Read-only mapping view of the stored files (SHA-256 to bytes)."""

    def __init__(self, storage: Storage):
        self._storage = storage

    def __getitem__(self, sha256: str) -> bytes:
        if not self._storage.has_file(sha256):
            raise KeyError(sha256)
        return self._storage.files.get(sha256)

    def __contains__(self, sha256: object) -> bool:
        return isinstance(sha256, str) and self._storage.has_file(sha256)

    def __iter__(self) -> Iterator[str]:
        rows = self._storage.db.query("SELECT sha256 FROM files ORDER BY sha256")
        return iter([row["sha256"] for row in rows])

    def __len__(self) -> int:
        return self._storage.db.query("SELECT COUNT(*) AS n FROM files")[0]["n"]

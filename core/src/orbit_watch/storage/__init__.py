"""Storage: one PostgreSQL database (phase 1, step 1.5; PostgreSQL since phase 4, step 4.1).

Decision P4-04, which replaced P-02: PostgreSQL wherever the service keeps state, in
production, in the local stack and in the tests. Schema changes are numbered plain-SQL
migrations. Files (requests, observations, reports) are kept in the database by their
SHA-256; a hash identifies a file, it does not replace keeping it, so files are never
deleted.

A database is named by a libpq connection string or URL (``postgresql://…``). A
``search_path`` in its ``options`` selects a schema; the tests give every test one.

Any number of service processes can share one schema (step 4.2, decision P4-06). Every
transaction takes the schema's advisory lock first, so changes happen one at a time. A
service keeps a copy of its state in memory: every change goes through to the database
in the same transaction, and a transaction that changes anything adds one to the state's
version (``service_state``). When a transaction begins, its hooks compare that version with
the one the process last saw, and the service reloads its copy if another process changed
the state, or if a transaction of its own was rolled back.

psycopg is imported only when a database is opened, so the command-line tools that keep
no state need neither psycopg nor a database.
"""

from __future__ import annotations

import functools
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib import resources
from typing import Any

from orbit_watch.canonical import sha256_bytes

_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ROLE_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_READS = ("SELECT", "WITH", "SHOW")


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
        self._conninfo = conninfo
        self.connection = self._connect()
        self._depth = 0
        self._dirty = False
        self._state_table = False
        # The role every transaction runs as (``use_role``): None runs as the user itself.
        self.role: str | None = None
        self._begin_hooks: list[Callable[[Database], None]] = []
        # The state version this process last saw (None: reload at the next transaction).
        self.version_seen: int | None = None
        row = self.query(
            "SELECT current_schema() AS s, hashtext('orbit-watch/' || current_database() "
            "|| '/' || current_schema()) AS k"
        )[0]
        if row["s"] is None:
            self.close()
            raise StorageError("cannot_open", "the database's search_path names no schema")
        self.schema = row["s"]
        self._lock_key = row["k"]

    def _connect(self) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        try:
            # The connection may be used from a server's worker threads; callers
            # serialise access (the API holds one lock around every call). No server-side
            # prepared statements, so that a pooler in transaction mode works (step 4.5).
            return psycopg.connect(
                self._conninfo, autocommit=True, row_factory=dict_row, prepare_threshold=None
            )
        except psycopg.Error as error:
            # libpq's message names the host and the user, never the password.
            raise StorageError("cannot_open", f"cannot open the database: {error}") from None

    def _reconnect_if_lost(self, error: BaseException) -> bool:
        """After ``error`` outside a transaction: if the connection is gone, open a new one
        and say so. A server that scales to zero, or a restart, closes connections; a
        long-lived process then carries on (step 4.5)."""
        import psycopg

        if self._depth or not isinstance(error, psycopg.OperationalError):
            return False
        if not (self.connection.closed or getattr(self.connection, "broken", False)):
            return False
        self.close()
        self.connection = self._connect()
        return True

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

    def add_begin_hook(self, hook: Callable[[Database], None]) -> None:
        """Run ``hook`` at the start of every outermost transaction, under the lock."""
        self._begin_hooks.append(hook)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One atomic unit of work, under the schema's advisory lock. Nested calls join the
        outer transaction."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        try:
            begun = self._begin()
        except BaseException as error:
            if not self._reconnect_if_lost(error):
                raise
            begun = self._begin()
        self._depth = 1
        self._dirty = False
        try:
            with begun:
                for hook in self._begin_hooks:
                    hook(self)
                yield
                if self._dirty and self._has_state_table():
                    row = self.connection.execute(
                        "UPDATE service_state SET version = version + 1 WHERE id = 1 "
                        "RETURNING version"
                    ).fetchone()
                    self.version_seen = row["version"]
        except BaseException:
            if self._dirty:
                # The process's copy may be ahead of the database: reload it next time.
                self.version_seen = None
            raise
        finally:
            self._depth = 0
            self._dirty = False

    def _begin(self) -> Any:
        """Begin the outermost transaction: its role and the schema's lock. Returns a
        context manager that commits it, or rolls it back on an error."""
        transaction = self.connection.transaction()
        transaction.__enter__()
        try:
            if self.role is not None:
                from psycopg import sql

                # For this transaction only, so that it holds behind a pooler too.
                self.connection.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(self.role))
                )
            self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (self._lock_key,))
        except BaseException:
            transaction.__exit__(*sys.exc_info())
            raise
        return _Entered(transaction)

    def _has_state_table(self) -> bool:
        if not self._state_table:
            self._state_table = bool(
                self.connection.execute("SELECT to_regclass('service_state') AS t").fetchone()["t"]
            )
        return self._state_table

    def use_role(self, role: str) -> None:
        """Make sure that ``role`` exists and may read and write this schema's tables, and
        nothing else, then run every transaction as it (step 4.5, decision P4-10). The
        connection's own user, which ran the migrations, must be allowed to create roles;
        it becomes a member of ``role`` so that it may switch to it. Run after ``migrate``,
        so that new tables are granted too."""
        from psycopg import sql

        if not _ROLE_RE.fullmatch(role):
            raise StorageError("bad_role", f"not a role name: {role!r}")
        name, schema = sql.Identifier(role), sql.Identifier(self.schema)
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (self._lock_key,))
            exists = self.connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone()
            if not exists:
                self.connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(name))
            for statement in (
                "GRANT {role} TO CURRENT_USER",
                "GRANT USAGE ON SCHEMA {schema} TO {role}",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {role}",
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {role}",
            ):
                self.connection.execute(sql.SQL(statement).format(role=name, schema=schema))
        self.role = role

    def current_version(self) -> int:
        """The state's version in the database."""
        return self.query("SELECT version FROM service_state WHERE id = 1")[0]["version"]

    def execute(self, sql: str, parameters: tuple[Any, ...] = (), *, state: bool = True) -> Any:
        """Run one statement. A change outside a transaction gets one of its own. With
        ``state=False`` a change leaves the state's version alone: it touches nothing that a
        process keeps in memory (keys, sessions, limits), so no other process reloads."""
        if not sql.lstrip().upper().startswith(_READS):
            if not self._depth:  # a change on its own: in a transaction of its own
                with self.transaction():
                    return self.execute(sql, parameters, state=state)
            if state:
                self._dirty = True
        try:
            return self._run(sql, parameters)
        except BaseException as error:
            if not self._reconnect_if_lost(error):
                raise
            return self._run(sql, parameters)

    def _run(self, sql: str, parameters: tuple[Any, ...]) -> Any:
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

    def migrate(self, up_to: int | None = None) -> list[int]:
        """Apply the migrations that are missing, up to version ``up_to`` (default: all;
        a restore stops at its backup's version, step 4.6). Returns the versions applied."""
        applied = []
        with self.transaction():
            self.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, sha256 TEXT NOT NULL)"
            )
            done = {row["version"]: row for row in self.query("SELECT * FROM schema_migrations")}
            for version, name, sql in available_migrations():
                if up_to is not None and version > up_to:
                    break
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


class _Entered:
    """A transaction already begun: leaving it commits it, or rolls it back on an error."""

    def __init__(self, transaction: Any):
        self._transaction = transaction

    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: Any) -> Any:
        return self._transaction.__exit__(*exc)


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

    def __init__(self, conninfo: str, role: str | None = None):
        self.db = Database(conninfo)
        try:
            self.db.migrate()
            if role is not None:
                self.db.use_role(role)
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

"""Storage for phase 1 (step 1.5): SQLite and content-addressed files.

Decision P-02: SQLite from the Python standard library, schema changes as
numbered plain-SQL migrations, and observation files and reports kept in a
directory by their SHA-256. A hash identifies a file; it does not replace
keeping it, so files are never deleted.

One process at a time: the database is opened in SQLite's exclusive locking
mode, and a second process that opens it gets ``StorageError("in_use")``. The
service keeps its working state in memory and writes every change through to
the database inside one transaction per operation.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Any

from orbit_watch.canonical import sha256_bytes

_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


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


class Database:
    """A SQLite database for one Orbit Watch service."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        try:
            self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=0)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA locking_mode = EXCLUSIVE")
            # Take the exclusive lock now, so a second process fails at once.
            self.connection.execute("BEGIN EXCLUSIVE")
            self.connection.execute("COMMIT")
        except sqlite3.OperationalError as error:
            if "locked" in str(error):
                raise StorageError("in_use", f"{self.path} is used by another process") from None
            raise StorageError("cannot_open", f"cannot open {self.path}: {error}") from None
        self._depth = 0

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

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
        self.connection.execute("BEGIN IMMEDIATE")
        self._depth = 1
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")
        finally:
            self._depth = 0

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, parameters)

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return self.connection.execute(sql, parameters).fetchall()

    def schema_version(self) -> int:
        if not self._has_migrations_table():
            return 0
        row = self.query("SELECT MAX(version) AS v FROM schema_migrations")[0]
        return row["v"] or 0

    def _has_migrations_table(self) -> bool:
        return bool(
            self.query(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            )
        )

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
    """Files kept by their SHA-256 under ``root/ab/abcdef...``. Never deleted."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, sha256: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise StorageError("bad_hash", f"not a SHA-256: {sha256!r}")
        return self.root / sha256[:2] / sha256

    def put(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        target = self.path(digest)
        if target.exists():
            return digest
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return digest

    def get(self, sha256: str) -> bytes:
        try:
            data = self.path(sha256).read_bytes()
        except FileNotFoundError:
            raise StorageError("missing_file", f"file {sha256} is missing") from None
        if sha256_bytes(data) != sha256:
            raise StorageError("corrupt_file", f"file {sha256} does not match its hash")
        return data

    def __contains__(self, sha256: str) -> bool:
        return self.path(sha256).exists()


class Storage:
    """A service's database and file store in one directory."""

    DATABASE = "orbit-watch.sqlite3"
    FILES = "files"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.directory / self.DATABASE)
        self.db.migrate()
        self.files = FileStore(self.directory / self.FILES)

    def close(self) -> None:
        self.db.close()

    def put_file(self, data: bytes) -> str:
        """Keep a file. A rolled-back transaction can leave an unlisted file on disk,
        which is harmless: files are addressed by content."""
        digest = self.files.put(data)
        self.db.execute(
            "INSERT INTO files (sha256, size) VALUES (?, ?) ON CONFLICT (sha256) DO NOTHING",
            (digest, len(data)),
        )
        return digest

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

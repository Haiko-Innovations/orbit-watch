"""Backups of the service's database (phase 4, step 4.6; decision D-39).

A backup is a gzipped tar archive, encrypted with age to the maintainer's public key
before it leaves the service. Inside are ``manifest.json`` and, for each table, its rows
in PostgreSQL's ``COPY`` text format (``tables/<name>.copy``). The manifest names the
schema's version, and each table's columns, row count and SHA-256.

The service takes a backup in one transaction, under the schema's advisory lock, so it
is consistent: every change takes the same lock. A backup leaves out what the service
needs only for a while and what a restore should not bring back: sessions, sign-in
challenges, limit counts and the copies of answers kept for idempotency.

A restore goes into an empty database. It applies the migrations up to the backup's
version, loads the rows, checks them against the manifest, and then applies the newer
migrations, so a newer version of the service restores an older backup. A backup from a
newer version is refused.

Anyone with the archive and ``age -d -i key.txt`` can read it without this code: the
format is age's own (https://age-encryption.org/v1), then tar and gzip.

psycopg and pyrage are imported only when they are needed (the ``api`` extra).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tarfile
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from orbit_watch import __version__
from orbit_watch.timeutil import format_utc

FORMAT = "orbit-watch-backup"
FORMAT_VERSION = 1
AGE_HEADER = b"age-encryption.org/v1\n"
# What a backup leaves out: the migrations' own record (a restore runs them), and what
# lives for hours at most and should not come back (decision D-37, personal-data.md).
SKIPPED = ("schema_migrations", "sessions", "signin_challenges", "rate_limits", "idempotency")
_NAME_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")


class BackupError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- encryption


def recipient(text: str) -> Any:
    """An age public key (``age1…``), checked."""
    from pyrage import RecipientError, x25519

    try:
        return x25519.Recipient.from_str(text.strip())
    except RecipientError:
        raise BackupError("bad_recipient", "not an age public key (age1…)") from None


def identity(text: str) -> Any:
    """The age private key in ``text``: an identity file as ``age-keygen`` writes it, or
    the key alone. The error never repeats the text."""
    from pyrage import IdentityError, x25519

    for line in text.splitlines():
        if line.strip().startswith("AGE-SECRET-KEY-"):
            try:
                return x25519.Identity.from_str(line.strip())
            except IdentityError:
                break
    raise BackupError("bad_identity", "no age private key (AGE-SECRET-KEY-1…) in the file")


def encrypt(data: bytes, public_key: str) -> bytes:
    import pyrage

    return pyrage.encrypt(data, [recipient(public_key)])


def decrypt(data: bytes, private_key: str) -> bytes:
    import pyrage

    try:
        return pyrage.decrypt(data, [identity(private_key)])
    except pyrage.DecryptError as error:
        raise BackupError("cannot_decrypt", f"the backup cannot be decrypted: {error}") from None


def is_encrypted(data: bytes) -> bool:
    return data.startswith(AGE_HEADER)


# ---------------------------------------------------------------- taking a backup


def _tables_in_order(db: Any) -> list[str]:
    """The schema's tables, every table after the tables its foreign keys name, without
    ``SKIPPED``."""
    tables = sorted(db.tables() - set(SKIPPED))
    rows = db.query(
        "SELECT child.relname AS child, parent.relname AS parent "
        "FROM pg_constraint c "
        "JOIN pg_class child ON child.oid = c.conrelid "
        "JOIN pg_class parent ON parent.oid = c.confrelid "
        "JOIN pg_namespace n ON n.oid = child.relnamespace "
        "WHERE c.contype = 'f' AND n.nspname = current_schema()"
    )
    needs = {table: set() for table in tables}
    for row in rows:
        if row["child"] in needs and row["parent"] in needs and row["child"] != row["parent"]:
            needs[row["child"]].add(row["parent"])
    ordered: list[str] = []
    while needs:
        ready = sorted(t for t, parents in needs.items() if not parents - set(ordered))
        if not ready:
            raise BackupError("cyclic_tables", f"the tables' foreign keys form a cycle: {needs}")
        ordered.extend(ready)
        for table in ready:
            del needs[table]
    return ordered


def _columns(db: Any, table: str) -> list[str]:
    """The columns that ``COPY`` can write back: all but generated ones."""
    rows = db.query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = ? AND is_generated = 'NEVER' "
        "ORDER BY ordinal_position",
        (table,),
    )
    return [row["column_name"] for row in rows]


def _copy_statement(table: str, columns: Iterable[str], direction: str) -> Any:
    from psycopg import sql

    return sql.SQL("COPY {} ({}) " + direction).format(
        sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    )


def take(db: Any, now: datetime) -> bytes:
    """The service's tables as a backup archive, unencrypted. Call it in a transaction
    (``db.transaction()``), which holds the lock that every change takes."""
    if not db.in_transaction:
        raise BackupError("no_transaction", "a backup is taken in one transaction")
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "taken_at": format_utc(now),
        "service_version": __version__,
        "schema_version": db.schema_version(),
        "skipped": list(SKIPPED),
        "tables": [],
    }
    contents: dict[str, bytes] = {}
    cursor = db.connection.cursor()
    for table in _tables_in_order(db):
        columns = _columns(db, table)
        buffer = io.BytesIO()
        with cursor.copy(_copy_statement(table, columns, "TO STDOUT")) as copy:
            for chunk in copy:
                buffer.write(chunk)
        data = buffer.getvalue()
        contents[table] = data
        manifest["tables"].append(
            {
                "name": table,
                "columns": columns,
                "rows": data.count(b"\n"),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return _archive(manifest, contents, now)


def _archive(manifest: dict[str, Any], contents: dict[str, bytes], now: datetime) -> bytes:
    raw = io.BytesIO()
    # The same backup makes the same archive: no names, times or owners of this machine.
    members = [("manifest.json", json.dumps(manifest, indent=2).encode() + b"\n")]
    members += [(f"tables/{name}.copy", data) for name, data in contents.items()]
    with (
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=int(now.timestamp())) as zipped,
        tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), int(now.timestamp()), 0o600
            tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


# ---------------------------------------------------------------- reading and restoring


def read(archive: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """The manifest and each table's rows, checked against the manifest's hashes."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            files: dict[str, bytes] = {}
            for member in tar.getmembers():
                if not member.isfile():
                    raise BackupError("bad_archive", f"unexpected entry {member.name!r}")
                extracted = tar.extractfile(member)
                files[member.name] = extracted.read() if extracted else b""
    except (tarfile.TarError, OSError, EOFError) as error:
        raise BackupError("bad_archive", f"not a backup archive: {error}") from None
    try:
        manifest = json.loads(files.pop("manifest.json"))
    except (KeyError, ValueError):
        raise BackupError("bad_archive", "the archive has no readable manifest.json") from None
    if manifest.get("format") != FORMAT or manifest.get("format_version") != FORMAT_VERSION:
        raise BackupError(
            "bad_archive",
            f"not an {FORMAT} archive of version {FORMAT_VERSION}: "
            f"{manifest.get('format')!r} {manifest.get('format_version')!r}",
        )
    tables: dict[str, bytes] = {}
    for entry in manifest["tables"]:
        data = files.pop(f"tables/{entry['name']}.copy", None)
        if data is None:
            raise BackupError("bad_archive", f"the rows of {entry['name']} are missing")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise BackupError("bad_archive", f"the rows of {entry['name']} do not match")
        tables[entry["name"]] = data
    if files:
        raise BackupError("bad_archive", f"unexpected files: {sorted(files)}")
    return manifest, tables


def restore(db: Any, archive: bytes) -> dict[str, Any]:
    """Restore an unencrypted backup archive into ``db``, which must be empty: no tables in
    its schema. Returns the manifest, with the schema's version after the restore."""
    from orbit_watch.storage import available_migrations

    manifest, tables = read(archive)
    version = manifest["schema_version"]
    latest = max(v for v, _, _ in available_migrations())
    if version > latest:
        raise BackupError(
            "newer_schema",
            f"the backup has schema version {version}; this version of Orbit Watch knows "
            f"up to {latest}: restore it with a newer version",
        )
    if db.tables():
        raise BackupError(
            "not_empty", f"restore into an empty database: schema {db.schema} has tables"
        )
    db.migrate(up_to=version)
    entries = manifest["tables"]
    expected = db.tables() - set(SKIPPED)
    if expected != {entry["name"] for entry in entries}:
        raise BackupError(
            "bad_archive",
            f"the backup's tables do not match schema version {version}: "
            f"{sorted(expected ^ {entry['name'] for entry in entries})}",
        )
    cursor = db.connection.cursor()
    with db.transaction():
        # Rows that the migrations themselves inserted make way for the backup's. The
        # state's version stays the backup's: nothing else uses this database yet.
        for entry in reversed(entries):
            db.execute(f"DELETE FROM {_quoted(entry['name'])}", state=False)
        for entry in entries:
            statement = _copy_statement(entry["name"], entry["columns"], "FROM STDIN")
            with cursor.copy(statement) as copy:
                copy.write(tables[entry["name"]])
            found = db.query(f"SELECT count(*) AS n FROM {_quoted(entry['name'])}")[0]["n"]
            if found != entry["rows"]:
                raise BackupError(
                    "bad_archive",
                    f"{entry['name']}: {found} rows restored, the manifest says {entry['rows']}",
                )
        _reset_identities(db)
    db.migrate()
    return {**manifest, "restored_schema_version": db.schema_version()}


def _quoted(name: str) -> str:
    """A table or column of the service's schema, quoted for SQL. The names come from the
    schema itself; a restore has already checked the backup's names against them."""
    if not _NAME_RE.fullmatch(name):
        raise BackupError("bad_archive", f"not a table or column name: {name!r}")
    return f'"{name}"'


def _reset_identities(db: Any) -> None:
    """Identity columns continue after the restored rows."""
    rows = db.query(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND is_identity = 'YES'"
    )
    for row in rows:
        table, column = _quoted(row["table_name"]), _quoted(row["column_name"])
        db.query(
            f"SELECT setval(pg_get_serial_sequence(?, ?), COALESCE(MAX({column}), 0) + 1, "
            f"false) FROM {table}",
            (table, row["column_name"]),
        )

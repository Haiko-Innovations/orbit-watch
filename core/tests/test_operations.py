"""Backups, restores and read-only mode (phase 4, step 4.6; decision D-39).

A backup goes through the API, as the public service's schedule takes it, is decrypted
with the maintainer's key, and is restored into a new database, which must then hold
exactly what the first one held. Everything is SIMULATED.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from test_api import ACCEPTABLE, REQUESTER, Client, funded_request, world  # noqa: F401

from orbit_watch import backup
from orbit_watch.api import create_app
from orbit_watch.canonical import sha256_bytes
from orbit_watch.cli import ServeError, build_parser, main, serve_app
from orbit_watch.service import open_service
from orbit_watch.storage import Database, available_migrations

x25519 = pytest.importorskip("pyrage").x25519
TOKEN = "a-backup-token-for-tests"
NOW = datetime(2026, 11, 17, 3, 23, tzinfo=UTC)


@pytest.fixture
def keypair():
    """A new age key pair: (private key, public key)."""
    secret = x25519.Identity.generate()
    return str(secret), str(secret.to_public())


def settled_request(world):  # noqa: F811
    """A request delivered, verified and settled: files, ledger, keys, idempotency."""
    requester, station = funded_request(world)
    client, clock = world["client"], world["clock"]
    clock.at("2026-11-02T04:00:00Z")
    response = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": sha256_bytes(ACCEPTABLE)},
    )
    assert response.status_code == 200, response.text
    clock.at("2026-11-03T04:00:01Z")
    assert client.call("POST", "/v1/admin/tick", world["admin"]).status_code == 200
    return requester, station


def contents(conninfo, *, skipped=backup.SKIPPED):
    """Every row of every table but ``skipped``, comparable. The state's version is left
    out: opening a database (its migrations) counts as a change, so it moves on."""
    with Database(conninfo) as db:
        return {
            table: sorted(
                json.dumps(
                    {k: v for k, v in row.items() if (table, k) != ("service_state", "version")},
                    sort_keys=True,
                    default=repr,
                )
                for row in db.query(f'SELECT * FROM "{table}"')
            )
            for table in sorted(db.tables() - set(skipped))
        }


def backup_app(world, public_key, **options):  # noqa: F811
    app = create_app(
        world["service"],
        clock=world["clock"],
        backup_token=TOKEN,
        backup_recipient=public_key,
        **options,
    )
    return TestClient(app)


def take_over_http(world, keypair):  # noqa: F811
    private_key, public_key = keypair
    reply = backup_app(world, public_key).get(
        "/v1/internal/backup", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert reply.status_code == 200, reply.text
    return reply, backup.decrypt(reply.content, private_key)


# ---------------------------------------------------------------- backups


def test_a_backup_restores_every_table_as_it_was(world, make_database, keypair):  # noqa: F811
    requester, _station = settled_request(world)
    reply, archive = take_over_http(world, keypair)
    assert reply.content.startswith(backup.AGE_HEADER)  # encrypted before it left
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["content-disposition"].endswith('.tar.gz.age"')
    assert reply.headers["content-type"] == "application/octet-stream"

    target = make_database()
    with Database(target) as db:
        result = backup.restore(db, archive)
    latest = max(v for v, _, _ in available_migrations())
    assert result["schema_version"] == result["restored_schema_version"] == latest
    assert contents(target) == contents(world["database"])
    files = next(entry for entry in result["tables"] if entry["name"] == "files")
    assert files["rows"] >= 3  # the request, the observations and the report

    # The restored database is a service: the same request, settled, and the same keys.
    service = open_service(target, world["registry"], world["context"])
    try:
        client = Client(TestClient(create_app(service, clock=world["clock"])))
        view = client.call("GET", "/v1/requests/SIM-REQ-0001", requester).json()
        assert view["summary"]["status"] == "settled"
        assert client.call("GET", f"/v1/balances/{REQUESTER}", requester).json()["points"] == 895
        stored = client.call("GET", f"/v1/files/{sha256_bytes(ACCEPTABLE)}", requester)
        assert stored.content == ACCEPTABLE
    finally:
        service.storage.close()


def test_a_backup_leaves_out_what_lives_for_hours(world, make_database, keypair):  # noqa: F811
    """Sessions, sign-in challenges, limit counts and copies of answers (D-37)."""
    settled_request(world)
    with Database(world["database"]) as db:
        assert db.query("SELECT count(*) AS n FROM idempotency")[0]["n"] > 0
    _reply, archive = take_over_http(world, keypair)
    manifest, tables = backup.read(archive)
    assert set(manifest["skipped"]) == set(backup.SKIPPED)
    assert not set(tables) & set(backup.SKIPPED)
    target = make_database()
    with Database(target) as db:
        backup.restore(db, archive)
        assert db.query("SELECT count(*) AS n FROM idempotency")[0]["n"] == 0
        assert db.query("SELECT count(*) AS n FROM schema_migrations")[0]["n"] == len(
            available_migrations()
        )


def test_the_backup_route_needs_its_token(world, keypair):  # noqa: F811
    _private, public_key = keypair
    plain = TestClient(create_app(world["service"], clock=world["clock"]))
    reply = plain.get("/v1/internal/backup", headers={"Authorization": f"Bearer {TOKEN}"})
    assert reply.status_code == 404 and reply.json()["error"]["code"] == "not_found"
    http = backup_app(world, public_key)
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": f"Basic {TOKEN}"}):
        reply = http.get("/v1/internal/backup", headers=headers)
        assert reply.status_code == 401, headers
        assert reply.json()["error"]["code"] == "unauthorized"
    with pytest.raises(ValueError, match="public key"):
        create_app(world["service"], backup_token=TOKEN)
    with pytest.raises(backup.BackupError, match="age public key"):
        create_app(world["service"], backup_token=TOKEN, backup_recipient="age1nope")


def test_a_restore_needs_an_empty_database_and_a_schema_it_knows(world, make_database, keypair):  # noqa: F811
    settled_request(world)
    _reply, archive = take_over_http(world, keypair)
    with Database(world["database"]) as db, pytest.raises(backup.BackupError) as raised:
        backup.restore(db, archive)
    assert raised.value.code == "not_empty"

    manifest, tables = backup.read(archive)
    manifest["schema_version"] += 1
    newer = backup._archive(manifest, tables, NOW)
    with Database(make_database()) as db, pytest.raises(backup.BackupError) as raised:
        backup.restore(db, newer)
    assert raised.value.code == "newer_schema"


def test_a_damaged_or_foreign_backup_is_refused(world, make_database, keypair):  # noqa: F811
    settled_request(world)
    reply, archive = take_over_http(world, keypair)

    manifest, tables = backup.read(archive)
    tables["files"] = tables["files"].replace(b"\n", b"\n\n", 1)
    with pytest.raises(backup.BackupError, match="files do not match"):
        backup.read(backup._archive(manifest, tables, NOW))
    with pytest.raises(backup.BackupError) as raised:
        backup.read(b"not an archive at all")
    assert raised.value.code == "bad_archive"

    stranger = str(x25519.Identity.generate())
    with pytest.raises(backup.BackupError) as raised:
        backup.decrypt(reply.content, stranger)
    assert raised.value.code == "cannot_decrypt"
    tampered = bytearray(reply.content)
    tampered[-10] ^= 0xFF
    with pytest.raises(backup.BackupError):
        backup.decrypt(bytes(tampered), keypair[0])
    with pytest.raises(backup.BackupError) as raised:
        backup.decrypt(reply.content, "# a file with no key\nAGE-SECRET-KEY-1NOTAKEY\n")
    assert raised.value.code == "bad_identity"
    assert "NOTAKEY" not in str(raised.value)  # never repeats a private key


def test_an_older_backup_restores_into_the_newest_schema(make_database):
    """A newer version of the service restores an older version's backup."""
    latest = max(v for v, _, _ in available_migrations())
    source = make_database()
    content = b"SIMULATED file kept since an older schema"
    with Database(source) as db:
        db.migrate(up_to=latest - 1)
        with db.transaction():
            db.execute(
                "INSERT INTO files (sha256, size, content) VALUES (?, ?, ?)",
                (sha256_bytes(content), len(content), content),
            )
            archive = backup.take(db, NOW)
    target = make_database()
    with Database(target) as db:
        result = backup.restore(db, archive)
        assert result["schema_version"] == latest - 1
        assert result["restored_schema_version"] == latest
        assert db.query("SELECT content FROM files")[0]["content"] == content


def test_identity_columns_continue_after_a_restore(make_database):
    source = make_database()
    with Database(source) as db:
        db.migrate()
        with db.transaction():
            for index in range(3):
                db.execute(
                    "INSERT INTO chain_conflicts (tx_hash, log_index, request_id, code, message) "
                    "VALUES (?, ?, 'SIM-REQ-0001', 'sim', 'SIMULATED conflict')",
                    ("0xabc", index),
                )
            archive = backup.take(db, NOW)
    target = make_database()
    with Database(target) as db:
        backup.restore(db, archive)
        db.execute(
            "INSERT INTO chain_conflicts (tx_hash, log_index, request_id, code, message) "
            "VALUES ('0xdef', 0, 'SIM-REQ-0002', 'sim', 'SIMULATED conflict')"
        )
        seqs = [row["seq"] for row in db.query("SELECT seq FROM chain_conflicts ORDER BY seq")]
    assert len(seqs) == 4 and seqs[-1] == max(seqs[:-1]) + 1


def test_a_backup_is_taken_in_a_transaction(database):
    with Database(database) as db:
        db.migrate()
        with pytest.raises(backup.BackupError) as raised:
            backup.take(db, NOW)
    assert raised.value.code == "no_transaction"


def test_the_command_line_takes_and_restores_a_backup(
    world,  # noqa: F811
    make_database,
    keypair,
    tmp_path,
    capsys,
):
    settled_request(world)
    private_key, public_key = keypair
    key_file = tmp_path / "backup-key.txt"
    key_file.write_text(f"# created: SIMULATED\n# public key: {public_key}\n{private_key}\n")
    output = tmp_path / "orbit-watch.tar.gz.age"
    take = ["backup", "create", "--database", world["database"], "--output", str(output)]
    assert main([*take, "--recipient", public_key]) == 0
    assert output.read_bytes().startswith(backup.AGE_HEADER)
    assert main([*take, "--recipient", public_key]) == 2  # never overwrites
    assert "never overwrites" in capsys.readouterr().err

    target = make_database()
    restore = ["backup", "restore", str(output), "--database", target]
    assert main(restore) == 2  # encrypted, and no key given
    assert "--identity" in capsys.readouterr().err
    assert main([*restore, "--identity", str(key_file)]) == 0
    printed = capsys.readouterr().out
    assert "Restored the backup of" in printed and "files:" in printed
    assert contents(target) == contents(world["database"])
    assert main([*restore, "--identity", str(key_file)]) == 1  # no longer empty
    assert "not_empty" in capsys.readouterr().err
    assert private_key not in printed


# ---------------------------------------------------------------- read-only mode


def test_read_only_refuses_every_change_and_keeps_reading(world):  # noqa: F811
    requester, _station = funded_request(world)
    app = create_app(
        world["service"], clock=world["clock"], read_only=True, follow_secret="a-follow-secret"
    )
    client = Client(TestClient(app))
    health = client.call("GET", "/v1/health").json()
    assert health["read_only"] is True
    refused = client.call("POST", "/v1/requests/SIM-REQ-0001/cancel", requester)
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "read_only"
    view = client.call("GET", "/v1/requests/SIM-REQ-0001", requester)
    assert view.status_code == 200 and view.json()["record"]["status"] == "reserved"
    assert client.call("GET", "/v1/public/requests").status_code == 200
    follow = client.call(
        "GET", "/v1/internal/follow", headers={"Authorization": "Bearer a-follow-secret"}
    )
    assert follow.status_code == 503 and follow.json()["error"]["code"] == "read_only"
    # Nothing changed, and the usual service still changes things.
    normal = Client(TestClient(create_app(world["service"], clock=world["clock"])))
    assert normal.call("GET", "/v1/health").json()["read_only"] is False
    assert normal.call("POST", "/v1/requests/SIM-REQ-0001/cancel", requester).status_code != 503


def test_read_only_and_backups_are_set_up_by_serve(world, monkeypatch, keypair):  # noqa: F811
    _private, public_key = keypair
    for name in (
        "ORBIT_WATCH_READ_ONLY",
        "ORBIT_WATCH_BACKUP_TOKEN",
        "ORBIT_WATCH_BACKUP_RECIPIENT",
        "ORBIT_WATCH_DATABASE_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    args = build_parser().parse_args(["serve", "--database", world["database"]])

    def start(environ):
        app, service, lines = serve_app(args, environ=environ)
        service.storage.close()
        return app.state.api, lines

    api, lines = start({"ORBIT_WATCH_READ_ONLY": "1"})
    assert api.read_only and "READ-ONLY: every change is refused and the follower waits" in lines
    api, _ = start({"ORBIT_WATCH_READ_ONLY": "off"})
    assert not api.read_only and api.backup_token is None
    with pytest.raises(ServeError, match="READ_ONLY"):
        start({"ORBIT_WATCH_READ_ONLY": "maybe"})
    with pytest.raises(ServeError, match="age public key"):
        start({"ORBIT_WATCH_BACKUP_TOKEN": TOKEN})
    with pytest.raises(ServeError, match="--backup-recipient"):
        start({"ORBIT_WATCH_BACKUP_TOKEN": TOKEN, "ORBIT_WATCH_BACKUP_RECIPIENT": "age1nope"})
    api, lines = start(
        {"ORBIT_WATCH_BACKUP_TOKEN": TOKEN, "ORBIT_WATCH_BACKUP_RECIPIENT": public_key}
    )
    assert api.backup_token == TOKEN and api.backup_recipient == public_key
    assert any(public_key in line for line in lines)
    assert not any(TOKEN in line for line in lines)
    read_only = build_parser().parse_args(["serve", "--database", world["database"], "--read-only"])
    app, service, _ = serve_app(read_only, environ={})
    service.storage.close()
    assert app.state.api.read_only


def test_the_service_takes_a_backup_as_its_database_role(world, make_database, keypair):  # noqa: F811
    """On the public service every transaction runs as a role that may only read and
    write the tables (P4-10, D-38): enough for a backup."""
    settled_request(world)
    world["service"].storage.close()
    role = "orbit_watch_test_app"
    service = open_service(
        world["database"], world["registry"], world["context"], database_role=role
    )
    world["service"] = service
    private_key, public_key = keypair
    http = backup_app(world, public_key)
    reply = http.get("/v1/internal/backup", headers={"Authorization": f"Bearer {TOKEN}"})
    assert reply.status_code == 200, reply.text
    target = make_database()
    with Database(target) as db:
        backup.restore(db, backup.decrypt(reply.content, private_key))
    assert contents(target) == contents(world["database"])


def test_serve_in_read_only_mode_does_not_follow_the_chain_at_start(monkeypatch, capsys):
    """Found in the first restore drill (2026-11-17): ``serve`` caught up with the chain
    before answering, which writes, also in read-only mode."""
    import uvicorn

    from orbit_watch import cli

    synced = []

    class Chain:
        def sync(self):
            synced.append(True)

        def synced_block(self):
            return 59883274

    service = SimpleNamespace(chain=Chain(), storage=SimpleNamespace(close=lambda: None))
    app = SimpleNamespace(state=SimpleNamespace(api=SimpleNamespace(read_only=True)))
    monkeypatch.setattr(cli, "serve_app", lambda args: (app, service, []))
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: None)
    assert main(["serve", "--read-only"]) == 0
    assert "Read-only: the chain as last followed, block 59883274" in capsys.readouterr().out
    assert not synced

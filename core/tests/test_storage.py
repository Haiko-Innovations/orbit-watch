"""Storage (phase 1, step 1.5; PostgreSQL since step 4.1): migrations, files, the stored
ledger and restarts."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes

from orbit_watch import lifecycle as lc
from orbit_watch.canonical import sha256_bytes
from orbit_watch.lifecycle import Status
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import (
    RequestService,
    ServiceError,
    VerificationContext,
    open_service,
)
from orbit_watch.settlement import scenarios as sc
from orbit_watch.settlement.ledger import LedgerAdapter
from orbit_watch.settlement.stored_ledger import StoredLedgerAdapter
from orbit_watch.storage import Database, FileStore, StorageError, available_migrations
from orbit_watch.timeutil import parse_utc

REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"
SPLIT = lc.RewardSplit(observer=100, reviewer=10, platform_fee=5)
T0 = parse_utc("2026-11-01T12:00:00Z")
DELIVERY = parse_utc("2026-11-02T04:00:00Z")
ACCEPTABLE = (
    Path(__file__).resolve().parents[2] / "examples/simulated/datasets/acceptable/observations.json"
).read_bytes()


# ------------------------------------------------------------------ database


def test_migrations_from_an_empty_database(database):
    with Database(database) as db:
        assert db.schema_version() == 0
        assert db.migrate() == [v for v, _, _ in available_migrations()]
        assert db.schema_version() == len(available_migrations())
        assert db.migrate() == []  # nothing left to do
        assert {
            "requests",
            "files",
            "deliveries",
            "settlements",
            "review_tasks",
            "ledger_entries",
            "ledger_postings",
            "ledger_settled",
            "attestations",
            "schema_migrations",
            "governance_operations",
            "chain_attestations",
        } <= db.tables()


def test_changed_or_unknown_migrations_are_refused(database):
    with Database(database) as db:
        db.migrate()
        db.execute("UPDATE schema_migrations SET sha256 = 'x' WHERE version = 1")
        with pytest.raises(StorageError) as error:
            db.migrate()
        assert error.value.code == "migration_changed"
    with Database(database) as db:
        row = db.query("SELECT sha256 FROM schema_migrations WHERE version = 1")[0]
        assert row["sha256"] == "x"  # the failed migration run changed nothing else
        digest = sha256_bytes(available_migrations()[0][2].encode())
        db.execute("UPDATE schema_migrations SET sha256 = ? WHERE version = 1", (digest,))
        db.execute("INSERT INTO schema_migrations VALUES (99, 'future', 'y')")
        with pytest.raises(StorageError) as error:
            db.migrate()
        assert error.value.code == "newer_schema"


def test_one_process_at_a_time(database):
    with Database(database):
        with pytest.raises(StorageError) as error:
            Database(database)
        assert error.value.code == "in_use"
    Database(database).close()  # free again after closing


def test_schemas_are_separate_services(make_database):
    with Database(make_database()) as one, Database(make_database()) as two:
        one.migrate()
        assert two.tables() == set()  # another schema in the same database


def test_a_database_without_a_schema_or_server_is_refused(database):
    from psycopg.conninfo import make_conninfo

    with pytest.raises(StorageError) as error:
        Database(make_conninfo(database, options="-c search_path=nowhere"))
    assert error.value.code == "cannot_open"
    with pytest.raises(StorageError) as error:
        Database("postgresql://nobody:secret-password@127.0.0.1:1/none?connect_timeout=2")
    assert error.value.code == "cannot_open"
    assert "secret-password" not in str(error.value)


def test_transactions_roll_back_and_nest(database):
    with Database(database) as db:
        db.migrate()
        with pytest.raises(RuntimeError), db.transaction():
            db.execute(
                "INSERT INTO files (sha256, size, content) VALUES (?, 1, ?)", ("a" * 64, b"a")
            )
            with db.transaction():
                db.execute(
                    "INSERT INTO files (sha256, size, content) VALUES (?, 1, ?)", ("b" * 64, b"b")
                )
            raise RuntimeError("boom")
        assert db.query("SELECT COUNT(*) AS n FROM files")[0]["n"] == 0


# ------------------------------------------------------------------ files


def test_file_store_is_content_addressed_and_checks_integrity(database):
    with Database(database) as db:
        db.migrate()
        store = FileStore(db)
        digest = store.put(b"observations")
        assert digest == sha256_bytes(b"observations") and store.put(b"observations") == digest
        assert store.get(digest) == b"observations" and digest in store
        assert db.query("SELECT size FROM files")[0]["size"] == len(b"observations")
        db.execute("UPDATE files SET content = ? WHERE sha256 = ?", (b"tampered", digest))
        with pytest.raises(StorageError) as error:
            store.get(digest)
        assert error.value.code == "corrupt_file"
        with pytest.raises(StorageError) as error:
            store.get("0" * 64)
        assert error.value.code == "missing_file"
        with pytest.raises(StorageError) as error:
            store.get("../etc/passwd")
        assert error.value.code == "bad_hash"


# ------------------------------------------------------------------ ledger


def test_stored_ledger_passes_the_adapter_suite(make_database):
    opened = []

    def factory(budgets):
        db = Database(make_database())
        db.migrate()
        opened.append(db)
        ledger = StoredLedgerAdapter(db)
        for party, points in sorted(budgets.items()):
            ledger.grant(party, points, key=f"budget/{party}")
        return ledger

    assert sc.check_adapter(factory) == []
    for db in opened:
        rebuilt = StoredLedgerAdapter(db)
        assert rebuilt.total() == 0
        assert all(
            rebuilt.escrow(r) == 0 for r in {e.request_id for e in rebuilt.journal} if r is not None
        )
        db.close()


def test_stored_ledger_matches_the_memory_ledger(database):
    def drive(ledger):
        driver = sc.Driver(ledger, lc.create(sc.scenario_terms("SIM-SAME"), sc.T0))
        for step in sc.SCENARIOS[3].steps:
            driver.step(step)
        driver.settle(driver.record.updated_at)
        return ledger.export()

    memory = LedgerAdapter()
    memory.grant(sc.REQUESTER, 1000, key="budget")
    with Database(database) as db:
        db.migrate()
        stored = StoredLedgerAdapter(db)
        stored.grant(sc.REQUESTER, 1000, key="budget")
        assert drive(stored) == drive(memory)
        assert StoredLedgerAdapter(db).export() == memory.export()  # after a rebuild


# ------------------------------------------------------------------ service


def registry():
    return ReviewerRegistry.parse(packaged("reviewers.json"))


def context():
    return VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())


def h(hours):
    return DELIVERY + timedelta(hours=hours)


def steps():
    """A full request history: challenged by the requester, accepted 2-1, settled."""
    rid = "SIM-REQ-0001"

    def votes(service, now, approvals):
        record = service.records[rid]
        reviewers = record.reviewers
        for index, approve in enumerate(approvals):
            service.vote(rid, reviewers[index], approve, f"Reason {index}", now)

    return [
        lambda s: s.create(request_bytes(), REQUESTER, T0),
        lambda s: s.open(rid, REQUESTER, T0 + timedelta(minutes=1)),
        lambda s: s.fund(rid, REQUESTER, SPLIT, T0 + timedelta(minutes=2)),
        lambda s: s.reserve(rid, STATION, T0 + timedelta(minutes=5)),
        lambda s: s.deliver(rid, STATION, ACCEPTABLE, DELIVERY),
        lambda s: s.challenge(rid, REQUESTER, "Please check the timing", h(1)),
        lambda s: votes(s, h(2), [True]),
        lambda s: s.review(
            next(t for t, v in s.real_tasks.items() if v[1] == s.records[rid].reviewers[1]),
            s.records[rid].reviewers[1],
            False,
            "Timing looks off",
            h(3),
        ),
        lambda s: s.vote(rid, s.records[rid].reviewers[2], True, "Timing is fine", h(4)),
        lambda s: s.tick(h(100)),
    ]


def snapshot(service):
    return {
        "records": {k: v.to_document() for k, v in service.records.items()},
        "deliveries": dict(service.deliveries),
        "settlements": dict(service.settlements),
        "real_tasks": dict(service.real_tasks),
        "calibration": {k: t.to_document() for k, t in service.calibration_tasks.items()},
        "ledger": service.adapter.export(),
        "files": sorted(service.files),
    }


def test_state_survives_every_restart_and_matches_the_memory_service(database):
    memory = RequestService(LedgerAdapter(), registry(), context())
    memory.adapter.grant(REQUESTER, 1000, key="budget")
    for step in steps():
        step(memory)

    directory = database
    service = open_service(directory, registry(), context())
    service.adapter.grant(REQUESTER, 1000, key="budget")
    for step in steps():
        step(service)
        service.storage.close()  # restart after every step
        service = open_service(directory, registry(), context())
    assert snapshot(service) == snapshot(memory)
    record = service.records["SIM-REQ-0001"]
    assert record.status is Status.SETTLED and record.outcome is Status.ACCEPTED
    assert service.adapter.balance(STATION) == 100
    report = service.report("SIM-REQ-0001")
    assert json.loads(report)["verdict"] == "pass"
    assert service.files[sha256_bytes(ACCEPTABLE)] == ACCEPTABLE
    service.storage.close()


def test_a_refused_call_leaves_storage_unchanged(database):
    directory = database
    service = open_service(directory, registry(), context())
    service.create(request_bytes(), REQUESTER, T0)
    service.open("SIM-REQ-0001", REQUESTER, T0 + timedelta(minutes=1))
    before = snapshot(service)
    with pytest.raises(ServiceError) as error:  # no points granted
        service.fund("SIM-REQ-0001", REQUESTER, SPLIT, T0 + timedelta(minutes=2))
    assert error.value.code == "insufficient_points"
    assert snapshot(service) == before
    service.storage.close()
    reopened = open_service(directory, registry(), context())
    assert snapshot(reopened) == before
    assert reopened.records["SIM-REQ-0001"].status is Status.OPEN
    reopened.storage.close()


def test_a_crash_in_the_middle_of_a_call_rolls_everything_back(database, monkeypatch):
    directory = database
    service = open_service(directory, registry(), context())
    service.adapter.grant(REQUESTER, 1000, key="budget")
    for step in steps()[:4]:
        step(service)
    before = snapshot(service)

    def broken_attest(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(service.adapter, "attest", broken_attest)
    with pytest.raises(RuntimeError):
        service.deliver("SIM-REQ-0001", STATION, ACCEPTABLE, DELIVERY)
    assert snapshot(service) == before  # lifecycle, delivery and books all rolled back
    assert service.records["SIM-REQ-0001"].status is Status.RESERVED
    monkeypatch.undo()
    record = service.deliver("SIM-REQ-0001", STATION, ACCEPTABLE, DELIVERY)
    assert record.status is Status.CHALLENGE_PERIOD
    service.storage.close()


def test_a_second_process_cannot_open_the_same_service(database):
    service = open_service(database, registry(), context())
    with pytest.raises(StorageError) as error:
        open_service(database, registry(), context())
    assert error.value.code == "in_use"
    service.storage.close()


def test_ci_uses_the_tests_postgres_image(repo_root):
    """CI's service container, the tests' own container and the demo's run the same
    PostgreSQL."""
    from postgres import POSTGRES_IMAGE

    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f"image: {POSTGRES_IMAGE}" in workflow
    demo = (repo_root / "web" / "demo" / "serve.sh").read_text(encoding="utf-8")
    assert f'image="{POSTGRES_IMAGE}"' in demo

"""Storage (phase 1, step 1.5): migrations, files, the SQLite ledger and restarts."""

import itertools
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
from orbit_watch.settlement.sqlite_ledger import SqliteLedgerAdapter
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


def test_migrations_from_an_empty_database(tmp_path):
    with Database(tmp_path / "db.sqlite3") as db:
        assert db.schema_version() == 0
        assert db.migrate() == [v for v, _, _ in available_migrations()]
        assert db.schema_version() == len(available_migrations())
        assert db.migrate() == []  # nothing left to do
        tables = {
            row["name"] for row in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
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
        } <= tables


def test_changed_or_unknown_migrations_are_refused(tmp_path):
    path = tmp_path / "db.sqlite3"
    with Database(path) as db:
        db.migrate()
        db.execute("UPDATE schema_migrations SET sha256 = 'x' WHERE version = 1")
        with pytest.raises(StorageError) as error:
            db.migrate()
        assert error.value.code == "migration_changed"
    with Database(path) as db:
        row = db.query("SELECT sha256 FROM schema_migrations WHERE version = 1")[0]
        assert row["sha256"] == "x"  # the failed migration run changed nothing else
        digest = sha256_bytes(available_migrations()[0][2].encode())
        db.execute("UPDATE schema_migrations SET sha256 = ? WHERE version = 1", (digest,))
        db.execute("INSERT INTO schema_migrations VALUES (99, 'future', 'y')")
        with pytest.raises(StorageError) as error:
            db.migrate()
        assert error.value.code == "newer_schema"


def test_one_process_at_a_time(tmp_path):
    path = tmp_path / "db.sqlite3"
    with Database(path):
        with pytest.raises(StorageError) as error:
            Database(path)
        assert error.value.code == "in_use"
    Database(path).close()  # free again after closing


def test_transactions_roll_back_and_nest(tmp_path):
    with Database(tmp_path / "db.sqlite3") as db:
        db.migrate()
        with pytest.raises(RuntimeError), db.transaction():
            db.execute("INSERT INTO files (sha256, size) VALUES (?, 1)", ("a" * 64,))
            with db.transaction():
                db.execute("INSERT INTO files (sha256, size) VALUES (?, 1)", ("b" * 64,))
            raise RuntimeError("boom")
        assert db.query("SELECT COUNT(*) AS n FROM files")[0]["n"] == 0


# ------------------------------------------------------------------ files


def test_file_store_is_content_addressed_and_checks_integrity(tmp_path):
    store = FileStore(tmp_path / "files")
    digest = store.put(b"observations")
    assert digest == sha256_bytes(b"observations") and store.put(b"observations") == digest
    assert store.get(digest) == b"observations" and digest in store
    assert store.path(digest).parent.name == digest[:2]
    store.path(digest).write_bytes(b"tampered")
    with pytest.raises(StorageError) as error:
        store.get(digest)
    assert error.value.code == "corrupt_file"
    with pytest.raises(StorageError) as error:
        store.get("0" * 64)
    assert error.value.code == "missing_file"
    with pytest.raises(StorageError) as error:
        store.path("../etc/passwd")
    assert error.value.code == "bad_hash"


# ------------------------------------------------------------------ ledger


def test_sqlite_ledger_passes_the_adapter_suite(tmp_path):
    counter = itertools.count()
    opened = []

    def factory(budgets):
        db = Database(tmp_path / f"ledger-{next(counter)}.sqlite3")
        db.migrate()
        opened.append(db)
        ledger = SqliteLedgerAdapter(db)
        for party, points in sorted(budgets.items()):
            ledger.grant(party, points, key=f"budget/{party}")
        return ledger

    assert sc.check_adapter(factory) == []
    for db in opened:
        rebuilt = SqliteLedgerAdapter(db)
        assert rebuilt.total() == 0
        assert all(
            rebuilt.escrow(r) == 0 for r in {e.request_id for e in rebuilt.journal} if r is not None
        )
        db.close()


def test_sqlite_ledger_matches_the_memory_ledger(tmp_path):
    def drive(ledger):
        driver = sc.Driver(ledger, lc.create(sc.scenario_terms("SIM-SAME"), sc.T0))
        for step in sc.SCENARIOS[3].steps:
            driver.step(step)
        driver.settle(driver.record.updated_at)
        return ledger.export()

    memory = LedgerAdapter()
    memory.grant(sc.REQUESTER, 1000, key="budget")
    with Database(tmp_path / "l.sqlite3") as db:
        db.migrate()
        stored = SqliteLedgerAdapter(db)
        stored.grant(sc.REQUESTER, 1000, key="budget")
        assert drive(stored) == drive(memory)
        assert SqliteLedgerAdapter(db).export() == memory.export()  # after a rebuild


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


def test_state_survives_every_restart_and_matches_the_memory_service(tmp_path):
    memory = RequestService(LedgerAdapter(), registry(), context())
    memory.adapter.grant(REQUESTER, 1000, key="budget")
    for step in steps():
        step(memory)

    directory = tmp_path / "service"
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


def test_a_refused_call_leaves_storage_unchanged(tmp_path):
    directory = tmp_path / "service"
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


def test_a_crash_in_the_middle_of_a_call_rolls_everything_back(tmp_path, monkeypatch):
    directory = tmp_path / "service"
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


def test_a_second_process_cannot_open_the_same_service(tmp_path):
    service = open_service(tmp_path / "service", registry(), context())
    with pytest.raises(StorageError) as error:
        open_service(tmp_path / "service", registry(), context())
    assert error.value.code == "in_use"
    service.storage.close()

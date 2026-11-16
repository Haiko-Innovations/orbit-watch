"""The follower and the stateless service (phase 4, step 4.2; decision P4-06).

The service's own work (deadlines, results, settling) runs without anyone calling
``tick``: a schedule calls ``/v1/internal/follow`` with its secret, or ``serve --follow``
runs it in a thread. Any number of processes may share one database. Everything is LOCAL
and SIMULATED: a test PostgreSQL, a throw-away Anvil chain and the worthless TestUSD.
"""

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from starlette.testclient import TestClient

from orbit_watch import lifecycle as lc
from orbit_watch.api import FOLLOW_MAX_AGE, create_app, start_follower
from orbit_watch.lifecycle import Status
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.timeutil import parse_utc

SECRET = "a-local-test-secret-of-the-follower"
REQUESTER = "requester:sim-cubesat-team"
RID = "SIM-REQ-0001"
T0 = parse_utc("2026-11-01T12:00:00Z")
DEADLINE = parse_utc("2026-11-03T03:00:00Z")  # the request's delivery deadline


def stored(database):
    service = open_service(
        database,
        ReviewerRegistry.parse(packaged("reviewers.json")),
        VerificationContext(catalog=catalog_bytes(), policy=policy_bytes()),
    )
    service.adapter.grant(REQUESTER, 1000, key="budget")
    return service


def funded(service):
    service.create(request_bytes(), REQUESTER, T0)
    service.open(RID, REQUESTER, T0 + timedelta(minutes=1))
    service.fund(
        RID,
        REQUESTER,
        lc.RewardSplit(observer=100, reviewer=10, platform_fee=5),
        T0 + timedelta(minutes=2),
    )


class Clock:
    """Wall-clock time that the test moves."""

    def __init__(self, at: datetime):
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def follow(http, token=SECRET, method="post"):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return getattr(http, method)("/v1/internal/follow", headers=headers)


# --------------------------------------------------------------------------- the endpoint


def test_without_a_secret_there_is_no_follower_route(database):
    service = stored(database)
    http = TestClient(create_app(service))
    reply = follow(http)
    assert reply.status_code == 404 and reply.json()["error"]["code"] == "not_found"
    service.storage.close()


def test_the_follower_needs_its_secret(database):
    service = stored(database)
    http = TestClient(create_app(service, follow_secret=SECRET))
    for token in (None, "", "wrong", SECRET + "x", f"Basic {SECRET}"):
        reply = follow(http, token)
        assert reply.status_code == 401, token
        assert reply.json()["error"]["code"] == "unauthorized"
    assert follow(http).status_code == 200
    assert follow(http, method="get").status_code == 200  # Vercel's cron jobs call GET
    service.storage.close()


def test_a_request_expires_without_tick(database):
    service = stored(database)
    funded(service)
    clock = Clock(T0 + timedelta(hours=1))
    http = TestClient(create_app(service, clock=clock, follow_secret=SECRET))
    assert follow(http).json()["changed"] == []
    assert service.records[RID].status is Status.FUNDED

    clock.at = DEADLINE
    reply = follow(http).json()
    assert reply["changed"] == [RID] and reply["sent"] == []
    record = service.records[RID]
    assert record.status is Status.SETTLED and record.outcome is Status.EXPIRED
    assert follow(http).json()["changed"] == []  # done once
    service.storage.close()


# --------------------------------------------------------------------------- health


def test_the_follower_health_says_when_it_falls_behind(database):
    service = stored(database)
    wall = Clock(datetime(2026, 11, 16, 12, tzinfo=UTC))
    http = TestClient(create_app(service, wall_clock=wall, follow_secret=SECRET))
    reply = http.get("/v1/health/follower")
    assert reply.status_code == 503
    assert reply.json()["status"] == "never" and reply.json()["followed_at"] is None

    follow(http)
    reply = http.get("/v1/health/follower")
    assert reply.status_code == 200
    assert reply.json() == {
        "status": "ok",
        "followed_at": "2026-11-16T12:00:00.000Z",
        "age_seconds": 0,
        "max_age_seconds": FOLLOW_MAX_AGE,
        "synced_block": None,
    }
    wall.at += timedelta(seconds=FOLLOW_MAX_AGE)
    assert http.get("/v1/health/follower").status_code == 200
    wall.at += timedelta(seconds=1)
    reply = http.get("/v1/health/follower")
    assert reply.status_code == 503 and reply.json()["status"] == "behind"
    service.storage.close()


def test_the_health_of_one_process_shows_another_ones_follower(database):
    one, two = (
        stored(database),
        open_service(
            database,
            ReviewerRegistry.parse(packaged("reviewers.json")),
            VerificationContext(catalog=catalog_bytes(), policy=policy_bytes()),
        ),
    )
    follow(TestClient(create_app(one, follow_secret=SECRET)))
    assert TestClient(create_app(two)).get("/v1/health/follower").status_code == 200
    one.storage.close()
    two.storage.close()


# --------------------------------------------------------------------------- serve --follow


def test_serve_follow_runs_the_follower_in_a_thread(database):
    service = stored(database)
    funded(service)
    app = create_app(service, clock=Clock(DEADLINE))
    stop = threading.Event()
    thread = start_follower(app, 0.05, stop=stop)
    assert thread.daemon
    try:
        deadline = time.monotonic() + 20
        while app.state.api.follower_status()["followed_at"] is None:
            assert time.monotonic() < deadline, "the follower did not run"
            time.sleep(0.05)
    finally:
        stop.set()
        thread.join(timeout=20)
    assert not thread.is_alive()
    service.refresh()
    assert service.records[RID].outcome is Status.EXPIRED
    service.storage.close()


# --------------------------------------------------------------------------- on a chain


@pytest.fixture
def world(database):
    from anvil import require_local_chain
    from chain_world import ChainWorld

    require_local_chain()
    made = ChainWorld(database)
    yield made
    made.stop()


def test_two_followers_settle_and_expire_once_without_tick(world):
    """Two processes follow one escrow from one database, at the same time: one request is
    settled after its challenge period and another expires undelivered, each by exactly
    one transaction of the verifier key, and nobody calls ``tick``."""
    from chain_world import VERIFIER
    from test_chain_service import RID as FIRST
    from test_chain_service import Api, deliver, open_and_fund

    second = "SIM-REQ-0002"
    api = Api(world)
    open_and_fund(api)
    open_and_fund(api, request=request_bytes(request_id=second), request_id=second)
    deliver(api, "acceptable")
    assert world.service.records[FIRST].status is Status.CHALLENGE_PERIOD
    # Past the first one's challenge period and the second one's delivery deadline.
    world.travel("2026-11-03T05:00:00Z")

    other = world.open()  # a second process on the same database
    followers = [
        create_app(service, follow_secret=SECRET).state.api for service in (world.service, other)
    ]
    start = threading.Barrier(2)
    results: list = [None, None]

    def run(index):
        start.wait()
        results[index] = followers[index].follow_once()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert all(result is not None for result in results), results
    sent = results[0]["sent"] + results[1]["sent"]
    assert len(sent) == 2 and len(set(sent)) == 2

    for service in (world.service, other):
        service.refresh()
        assert service.records[FIRST].outcome is Status.ACCEPTED
        assert service.records[second].outcome is Status.EXPIRED
        assert all(r.status is Status.SETTLED for r in service.records.values())
    rows = world.service.storage.db.query(
        "SELECT request_id FROM transactions WHERE party = ? AND action = 'settle'", (VERIFIER,)
    )
    assert sorted(row["request_id"] for row in rows) == [FIRST, second]
    assert world.chain.status(FIRST) == "Settled" and world.chain.status(second) == "Settled"
    # Following again changes nothing and sends nothing.
    again = followers[1].follow_once()
    assert again["changed"] == [] and again["sent"] == []
    other.storage.close()


def test_a_block_is_followed_once_it_is_deep_enough(world, make_database):
    """Events are applied once ``confirmations`` blocks follow their block; until then a
    mined transaction of the service counts as on its way, so it is not sent again."""
    from chain_world import VERIFIER

    from orbit_watch.chain.client import OrbitWatchChain
    from orbit_watch.chain.link import CONFIRMATIONS, ChainLink

    assert CONFIRMATIONS == {84532: 10, 31337: 0}
    assert world.link.confirmations == 0
    with pytest.raises(ValueError):
        ChainLink(world.chain, world.account(VERIFIER), confirmations=-1)

    chain = OrbitWatchChain(world.w3, world.chain.escrow.address)
    link = ChainLink(chain, world.account(VERIFIER), confirmations=3)
    service = open_service(
        make_database(),
        world.service.reviewers,
        VerificationContext(catalog=catalog_bytes(), policy=policy_bytes()),
        chain=link,
    )
    start = link.synced_block()
    world.local.rpc("anvil_mine", [hex(2)])
    link.sync()
    assert link.synced_block() == start  # two new blocks, neither three deep
    world.local.rpc("anvil_mine", [hex(4)])
    link.sync()
    assert link.synced_block() == chain.latest_block() - 3 == start + 3

    db = service.storage.db
    for tx_hash, block in (("0x" + "a" * 64, start + 3), ("0x" + "b" * 64, start + 4)):
        db.execute(
            "INSERT INTO transactions (tx_hash, party, action, request_id, status, block, "
            "reported_at) VALUES (?, ?, ?, ?, 'confirmed', ?, ?)",
            (tx_hash, VERIFIER, f"settle-{block}", RID, block, "2026-11-16T12:00:00.000Z"),
        )
    assert not link._pending(RID, f"settle-{start + 3}")  # followed already
    assert link._pending(RID, f"settle-{start + 4}")  # mined, not deep enough yet
    service.storage.close()

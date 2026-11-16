"""Personal data in the service (phase 4, step 4.4; decisions P4-09 and D-37).

Station coordinates to about a kilometre, deleting a station profile, ending every session
and the retention of what the service keeps (docs/personal-data.md). The points ledger
needs no chain; sessions belong to wallets, so their tests run on a LOCAL Anvil chain.
Everything is SIMULATED.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from helpers import packaged
from starlette.testclient import TestClient
from test_api import ACCEPTABLE, STATION, Client, funded_request, new_key, world  # noqa: F401

from orbit_watch.api import create_app, privacy
from orbit_watch.canonical import sha256_bytes
from orbit_watch.cli import _station_decimals, build_parser
from orbit_watch.timeutil import format_utc

PROFILE = f"/v1/stations/{STATION}/profile"
WALL = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


class WallClock:
    def __init__(self, now=WALL):
        self.now = now

    def __call__(self):
        return self.now


def public(world, wall=None):  # noqa: F811
    """The world's service as `orbit-watch serve` runs it: coordinates to two decimals."""
    app = create_app(
        world["service"],
        clock=world["clock"],
        station_decimals=privacy.STATION_DECIMALS,
        wall_clock=wall or WallClock(),
    )
    return Client(TestClient(app))


def template():
    return json.loads(packaged("stations/sim-cmos-gps.json"))  # SIM-ESPOO, 60.205, 24.655


def put(client, key, profile, idem):
    return client.call("PUT", PROFILE, key, {"profile": profile}, headers={"Idempotency-Key": idem})


def delete(client, key, idem, path=PROFILE):
    return client.call("DELETE", path, key, headers={"Idempotency-Key": idem})


# ---------------------------------------------------------------- coordinates to a kilometre


def test_a_profile_is_kept_to_two_decimals(world):  # noqa: F811
    station = new_key(world, STATION, "station")
    client = public(world)
    profile = template()
    profile["station"]["latitude_deg"] = 60.20537
    profile["station"]["longitude_deg"] = -24.65549
    saved = put(client, station, profile, "p1")
    assert saved.status_code == 200, saved.text
    place = saved.json()["profile"]["station"]
    assert (place["latitude_deg"], place["longitude_deg"]) == (60.21, -24.66)
    assert place["altitude_m"] == 40.0  # height says nothing of where a home is
    kept = client.call("GET", PROFILE, station).json()["profile"]["station"]
    assert (kept["latitude_deg"], kept["longitude_deg"]) == (60.21, -24.66)
    stored = world["service"].storage.db.query("SELECT profile_json FROM station_profiles")
    assert "60.20537" not in stored[0]["profile_json"]
    assert "60.20537" not in json.dumps(
        world["service"].storage.db.query("SELECT * FROM idempotency")
    )


def test_without_the_setting_a_profile_is_kept_as_given(world):  # noqa: F811
    """The local tools and the tests keep coordinates as they are (create_app's default)."""
    station = new_key(world, STATION, "station")
    profile = template()
    assert put(world["client"], station, profile, "p1").json()["profile"] == profile


def test_a_more_precise_delivery_is_refused_and_changes_nothing(world):  # noqa: F811
    _, station = funded_request(world)  # reserved by SIM-ESPOO
    client = public(world)
    path = "/v1/requests/SIM-REQ-0001/deliveries"
    assert json.loads(ACCEPTABLE)["station"]["latitude_deg"] == 60.205
    refused = client.call(
        "POST",
        path,
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": sha256_bytes(ACCEPTABLE)},
    )
    assert refused.status_code == 422
    error = refused.json()["error"]
    assert error["code"] == "too_precise"
    assert "2 decimals" in error["message"] and "latitude_deg" in error["message"]
    record = client.call("GET", "/v1/requests/SIM-REQ-0001", station).json()["record"]
    assert record["status"] == "reserved"
    assert sha256_bytes(ACCEPTABLE) not in world["service"].files  # not even kept

    # Observations simulated with the station's profile, kept to two decimals, pass.
    assert put(client, station, template(), "p1").status_code == 200
    made = client.call("POST", "/v1/requests/SIM-REQ-0001/simulate", station).json()
    body = made["observations"].encode("utf-8")
    place = json.loads(body)["station"]
    assert (place["latitude_deg"], place["longitude_deg"]) == (
        round(60.205, 2),
        round(24.655, 2),
    )
    delivered = client.call(
        "POST", path, station, content=body, headers={"Content-SHA256": made["sha256"]}
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["summary"]["automated_verdict"] == "pass"


def test_a_profile_saved_before_the_setting_simulates_to_two_decimals(world):  # noqa: F811
    _, station = funded_request(world)
    assert put(world["client"], station, template(), "p1").status_code == 200  # 60.205
    made = public(world).call("POST", "/v1/requests/SIM-REQ-0001/simulate", station).json()
    place = json.loads(made["observations"])["station"]
    assert place["latitude_deg"] == round(60.205, 2)


@pytest.mark.parametrize(
    ("place", "refused"),
    [
        ({"latitude_deg": 60.2, "longitude_deg": 24.66}, False),
        ({"latitude_deg": 60, "longitude_deg": -24}, False),
        ({"latitude_deg": 60.21, "longitude_deg": 24.655}, True),
        ({"latitude_deg": 60.2051, "longitude_deg": 24.66}, True),
        ({"latitude_deg": "60.20537", "longitude_deg": 24.66}, False),  # not a number: schema
    ],
)
def test_which_files_are_too_precise(place, refused):
    body = json.dumps({"station": {"id": "SIM-X", "altitude_m": 1.234, **place}}).encode()
    assert (privacy.too_precise(body, 2) is not None) is refused
    assert privacy.too_precise(b"not json", 2) is None  # verification says what is wrong
    assert privacy.too_precise(b"[1, 2]", 2) is None


# ---------------------------------------------------------------- deleting a profile


def test_a_station_deletes_its_profile(world):  # noqa: F811
    _, station = funded_request(world)
    other = new_key(world, "station:SIM-OULU", "station")
    requester = new_key(world, "requester:sim-other", "requester")
    client = public(world)
    assert put(client, station, template(), "p1").status_code == 200
    assert put(client, station, template(), "p2").status_code == 200
    db = world["service"].storage.db
    assert len(db.query("SELECT 1 FROM idempotency WHERE path = ?", (PROFILE,))) == 2

    assert delete(client, other, "d0").json()["error"]["code"] == "not_yourself"
    assert delete(client, requester, "d0").json()["error"]["code"] == "forbidden_role"
    deleted = delete(client, station, "d1")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"party": STATION, "deleted": True}
    assert client.call("GET", PROFILE, station).json()["error"]["code"] == "no_profile"
    simulate = client.call("POST", "/v1/requests/SIM-REQ-0001/simulate", station)
    assert simulate.json()["error"]["code"] == "no_profile"
    # The copies of its answers went with it: nothing of the place is left.
    left = json.dumps(db.query("SELECT * FROM idempotency"))
    assert "latitude_deg" not in left
    assert db.query("SELECT 1 FROM station_profiles") == []
    # Asked again, the same answer; a new deletion finds nothing.
    assert delete(client, station, "d1").headers["Idempotent-Replayed"] == "true"
    assert delete(client, station, "d2").json() == {"party": STATION, "deleted": False}


def test_an_administrator_deletes_a_station_profile(world):  # noqa: F811
    station = new_key(world, STATION, "station")
    client = public(world)
    assert put(client, station, template(), "p1").status_code == 200
    deleted = delete(client, world["admin"], "d1")
    assert deleted.json() == {"party": STATION, "deleted": True}
    assert client.call("GET", PROFILE, station).status_code == 404


def test_deleting_needs_an_idempotency_key(world):  # noqa: F811
    station = new_key(world, STATION, "station")
    refused = world["client"].call("DELETE", PROFILE, station)
    assert refused.json()["error"]["code"] == "idempotency_key_required"


# ---------------------------------------------------------------- idempotency for a day


def test_an_idempotency_key_is_remembered_for_a_day(world):  # noqa: F811
    station = new_key(world, STATION, "station")
    wall = WallClock()
    client = public(world, wall)
    profile = template()
    assert "Idempotent-Replayed" not in put(client, station, profile, "same").headers
    wall.now += timedelta(hours=23, minutes=59)
    assert put(client, station, profile, "same").headers["Idempotent-Replayed"] == "true"
    wall.now += timedelta(minutes=1)
    again = put(client, station, profile, "same")
    assert again.status_code == 200 and "Idempotent-Replayed" not in again.headers
    rows = world["service"].storage.db.query(
        "SELECT path, expires_at FROM idempotency WHERE party = ?", (STATION,)
    )
    expires = int((wall.now + timedelta(days=1)).timestamp())
    assert rows == [{"path": PROFILE, "expires_at": expires}]


# ---------------------------------------------------------------- the sweep


def test_the_sweep_deletes_what_is_no_longer_needed(database):
    from orbit_watch.storage import Storage

    storage = Storage(database)  # migrated
    db = storage.db
    now = WALL
    old, recent = format_utc(now - timedelta(hours=2)), format_utc(now - timedelta(minutes=30))
    later = format_utc(now + timedelta(hours=1))
    with db.transaction():
        for i, (expires, ended) in enumerate(
            [(later, None), (later, recent), (format_utc(now), None), (recent, None)]
        ):
            db.execute(
                "INSERT INTO sessions (token_hash, party, role, address, origin, created_at, "
                "expires_at, ended_at) VALUES (?, 'station:x', 'station', '0x1', 'o', ?, ?, ?)",
                (f"{i:064d}", old, expires, ended),
            )
        for nonce, expires in [("a", later), ("b", recent), ("c", old)]:
            db.execute(
                "INSERT INTO signin_challenges (nonce, address, origin, message, issued_at, "
                "expires_at) VALUES (?, '0x1', 'o', 'm', ?, ?)",
                (nonce, old, expires),
            )
        seconds = int(now.timestamp())
        for window, expires in [(1, seconds + 60), (2, seconds)]:
            db.execute(
                "INSERT INTO rate_limits (name, subject, window_start, hits, expires_at) "
                "VALUES ('public', 's', ?, 1, ?)",
                (window, expires),
            )
        for key, expires in [("k1", seconds + 60), ("k2", seconds - 1), ("k3", None)]:
            db.execute(
                "INSERT INTO idempotency (party, idempotency_key, request_hash, status_code, "
                "response_json, path, expires_at) VALUES ('p', ?, 'h', 200, '{}', '/', ?)",
                (key, expires),
            )
    with db.transaction():
        version = db.current_version()
    with db.transaction():
        removed = privacy.sweep(db, now)
    assert removed == {
        "sessions": 3,
        "sign_in_messages": 1,
        "limit_counts": 1,
        "idempotency_records": 2,
    }
    assert [r["token_hash"] for r in db.query("SELECT token_hash FROM sessions")] == [f"{0:064d}"]
    # A sign-in message stays an hour after it expires: a late answer hears "expired".
    assert sorted(r["nonce"] for r in db.query("SELECT nonce FROM signin_challenges")) == ["a", "b"]
    assert [r["window_start"] for r in db.query("SELECT window_start FROM rate_limits")] == [1]
    assert [r["idempotency_key"] for r in db.query("SELECT idempotency_key FROM idempotency")] == [
        "k1"
    ]
    with db.transaction():
        assert db.current_version() == version  # nobody reloads for it
    storage.close()


# ---------------------------------------------------------------- sessions (on a chain)


@pytest.fixture
def chain_world(database):
    from anvil import require_local_chain
    from chain_world import ChainWorld

    require_local_chain()
    made = ChainWorld(database)
    yield made
    made.stop()


def browser(chain_world, wall):
    from test_sessions import ORIGIN

    app = create_app(chain_world.service, origins=[ORIGIN], wall_clock=wall)
    return TestClient(app, base_url=ORIGIN)


def test_a_party_ends_its_sessions_in_every_browser(chain_world):
    from chain_world import REQUESTER as CHAIN_REQUESTER
    from chain_world import STATION as CHAIN_STATION
    from test_sessions import ORIGIN, register, sign_in

    wall = WallClock()
    station = register(chain_world, CHAIN_STATION)
    requester = register(chain_world, CHAIN_REQUESTER)
    laptop, phone, other = (browser(chain_world, wall) for _ in range(3))
    for http, account in ((laptop, station), (phone, station), (other, requester)):
        assert sign_in(http, account)[1].status_code == 200
    db = chain_world.service.storage.db
    assert len(db.query("SELECT 1 FROM sessions")) == 3

    assert laptop.delete("/v1/sessions").json()["error"]["code"] == "forbidden_origin"
    ended = laptop.delete("/v1/sessions", headers={"Origin": ORIGIN})
    assert ended.status_code == 200, ended.text
    assert ended.json() == {"party": CHAIN_STATION, "ended": 2}
    assert 'ow_session=""' in ended.headers["set-cookie"]
    assert phone.get("/v1/session").json() == {"session": None}  # the other browser too
    assert other.get("/v1/session").json()["session"]["party"] == CHAIN_REQUESTER
    rows = db.query("SELECT party FROM sessions")
    assert [r["party"] for r in rows] == [CHAIN_REQUESTER]
    again = phone.delete("/v1/sessions", headers={"Origin": ORIGIN})
    assert again.status_code == 401

    # Signing out deletes the session's row too.
    assert other.delete("/v1/session", headers={"Origin": ORIGIN}).status_code == 200
    assert db.query("SELECT 1 FROM sessions") == []


def test_the_follower_and_every_sign_in_sweep(chain_world):
    from chain_world import STATION as CHAIN_STATION
    from test_sessions import challenge, register, sign_in

    wall = WallClock()
    station = register(chain_world, CHAIN_STATION)
    http = browser(chain_world, wall)
    assert sign_in(http, station)[1].status_code == 200
    db = chain_world.service.storage.db
    assert len(db.query("SELECT 1 FROM sessions")) == 1
    assert len(db.query("SELECT 1 FROM signin_challenges")) == 1

    wall.now += timedelta(hours=13)  # the session (12 h) and the message (5 min) expired
    http.app.state.api.follow_once()
    assert db.query("SELECT 1 FROM sessions") == []
    assert db.query("SELECT 1 FROM signin_challenges") == []

    assert sign_in(http, station)[1].status_code == 200
    wall.now += timedelta(hours=13)
    assert challenge(http, station.address).status_code == 200  # sweeps, then asks anew
    assert db.query("SELECT 1 FROM sessions") == []
    assert len(db.query("SELECT 1 FROM signin_challenges")) == 1  # the new one


# ---------------------------------------------------------------- the command line


def test_serve_keeps_coordinates_to_two_decimals_by_default(monkeypatch):
    monkeypatch.delenv("ORBIT_WATCH_STATION_DECIMALS", raising=False)
    parsed = build_parser().parse_args(["serve"])
    assert parsed.station_decimals == "2" and parsed.access_log is False
    monkeypatch.setenv("ORBIT_WATCH_STATION_DECIMALS", "off")
    assert build_parser().parse_args(["serve"]).station_decimals == "off"
    assert _station_decimals("2") == 2 and _station_decimals("0") == 0
    assert _station_decimals(" OFF ") is None
    assert _station_decimals("9") == -1 and _station_decimals("1.5") == -1
    assert _station_decimals("-1") == -1


def test_serve_refuses_a_bad_precision(capsys, make_database):
    from orbit_watch.cli import main

    assert main(["serve", "--database", make_database(), "--station-decimals", "x"]) == 2
    assert "--station-decimals" in capsys.readouterr().err

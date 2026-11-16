"""Limits against abuse and the body limit (phase 4, step 4.3; decision P4-08).

Every limited endpoint: sign-in and sign-up attempts, new requests, uploads and quality
meter runs, per IP address and per party, answered with 429 and Retry-After. Everything is
LOCAL and SIMULATED.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from helpers import catalog_bytes, packaged, policy_bytes, request_bytes
from starlette.testclient import TestClient

from orbit_watch.api import MAX_BODY_BYTES, create_app, keys
from orbit_watch.api.limits import DEFAULTS, Limits, LimitsError, Rule, network_of
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service

START = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)  # a whole hour: windows start here


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


def only(**rules):
    """Limits with ``rules`` and nothing else, e.g. only(quality={"ip": Rule(2, 60)})."""
    return Limits(
        {name: {"ip": None, "party": None, **subjects} for name, subjects in rules.items()}
    )


class Stack:
    def __init__(self, database, limits, header=None):
        self.service = open_service(
            database,
            ReviewerRegistry.parse(packaged("reviewers.json")),
            VerificationContext(catalog=catalog_bytes(), policy=policy_bytes()),
        )
        self.wall = Clock(START)
        self.http = TestClient(
            create_app(
                self.service,
                clock=lambda: START,
                wall_clock=self.wall,
                limits=limits,
                client_ip_header=header,
            )
        )
        db = self.service.storage.db
        with db.transaction():
            self.keys = {
                party: keys.create_key(db, party, party.split(":")[0], START)
                for party in ("requester:sim-a", "requester:sim-b", "station:SIM-ESPOO")
            }
        self.count = 0

    def post(self, path, party=None, body=None, content=None, headers=None):
        self.count += 1
        all_headers = {"Idempotency-Key": f"k{self.count}", **(headers or {})}
        if party:
            all_headers["Authorization"] = f"Bearer {self.keys[party]}"
        if body is not None:
            content = json.dumps(body).encode()
        return self.http.post(path, content=content, headers=all_headers)

    def create(self, party, number, headers=None):
        document = json.loads(request_bytes(request_id=f"SIM-REQ-{number:04d}"))
        return self.post("/v1/requests", party, {"request": document}, headers=headers)

    def version(self):
        return self.service.storage.db.query("SELECT version FROM service_state")[0]["version"]

    def close(self):
        self.service.storage.close()


@pytest.fixture
def make_stack(database):
    made = []

    def make(limits, header=None):
        made.append(Stack(database, limits, header))
        return made[-1]

    yield make
    for stack in made:
        stack.close()


def refused(reply, retry_after=None):
    assert reply.status_code == 429, reply.text
    assert reply.json()["error"]["code"] == "rate_limited"
    if retry_after is not None:
        assert reply.headers["retry-after"] == str(retry_after)
    return True


# --------------------------------------------------------------------------- per party, per IP


def test_new_requests_are_limited_per_party_and_per_ip(make_stack):
    stack = make_stack(only(new_request={"ip": Rule(3, 3600), "party": Rule(2, 3600)}))
    a, b = "requester:sim-a", "requester:sim-b"
    assert stack.create(a, 1).status_code == 201
    stack.wall.at = START + timedelta(minutes=10)
    assert stack.create(a, 2).status_code == 201
    reply = stack.create(a, 3)
    assert refused(reply, retry_after=50 * 60)  # until the hour's window ends
    assert "per party" in reply.json()["error"]["message"]
    assert "SIM-REQ-0003" not in stack.service.records  # refused before it did anything
    # The refused call was not counted: the IP address has made two calls, not three.
    assert stack.create(b, 4).status_code == 201
    reply = stack.create(b, 5)
    assert refused(reply) and "per IP address" in reply.json()["error"]["message"]
    # A new window, new counts.
    stack.wall.at = START + timedelta(hours=1)
    assert stack.create(a, 6).status_code == 201


def test_uploads_are_limited_and_a_failed_call_counts(make_stack):
    stack = make_stack(only(upload={"party": Rule(2, 600)}))
    station = "station:SIM-ESPOO"
    path = "/v1/requests/SIM-REQ-0001/deliveries"
    for _ in range(2):  # no such request: refused, but counted
        reply = stack.post(path, station, content=b"{}")
        assert reply.status_code == 404, reply.text
    assert refused(stack.post(path, station, content=b"{}"), retry_after=600)
    # Other endpoints are not limited by it.
    assert stack.create("requester:sim-a", 1).status_code == 201


def test_the_quality_meter_is_limited_per_ip(make_stack):
    stack = make_stack(only(quality={"ip": Rule(2, 60)}), header="x-real-ip")

    def score(ip):
        return stack.http.post(
            "/v1/public/quality", content=b"not observations", headers={"X-Real-IP": ip}
        )

    for _ in range(2):
        assert score("192.0.2.10").status_code == 422  # not a file the meter reads
    assert refused(score("192.0.2.10"), retry_after=60)
    assert score("192.0.2.11").status_code == 422  # another address counts on its own
    # IPv6 addresses count per /64 network: one host or home.
    assert score("2001:db8:1:2::1").status_code == 422
    assert score("2001:db8:1:2:ffff::9").status_code == 422
    assert refused(score("2001:db8:1:2::abcd"))
    assert score("2001:db8:1:3::1").status_code == 422


PUBLIC = [
    "/v1/public/requests",
    "/v1/public/requests/SIM-REQ-0001",
    "/v1/public/files/" + "0" * 64,
    "/v1/public/open-requests",
    "/v1/public/targets",
    "/v1/public/station-templates",
    "/v1/public/attestations",
    "/v1/chain",
]


def test_every_public_page_is_limited_per_ip(make_stack):
    """Pages anyone may read without a key share one limit per IP address, so that the
    limits hold without a firewall in front (P4-05). Health checks are not limited."""
    stack = make_stack(only(public={"ip": Rule(len(PUBLIC), 600)}), header="x-real-ip")
    one, other = {"X-Real-IP": "192.0.2.1"}, {"X-Real-IP": "192.0.2.2"}
    for path in PUBLIC:
        assert stack.http.get(path, headers=one).status_code != 429, path
    for path in PUBLIC:
        assert refused(stack.http.get(path, headers=one)), path
        assert stack.http.get(path, headers=other).status_code != 429, path
    for path in ("/v1/health", "/v1/health/follower"):
        assert stack.http.get(path, headers=one).status_code != 429


def test_behind_a_proxy_the_last_address_counts(make_stack):
    stack = make_stack(only(quality={"ip": Rule(1, 60)}), header="x-forwarded-for")

    def score(value):
        return stack.http.post(
            "/v1/public/quality", content=b"x", headers={"X-Forwarded-For": value}
        )

    assert score("203.0.113.5, 198.51.100.7").status_code == 422
    # A caller can put anything first; the address the proxy added is the last one.
    assert refused(score("192.0.2.99, 198.51.100.7"))
    assert score("198.51.100.7, 203.0.113.5").status_code == 422


def test_without_a_trusted_header_the_connection_counts(make_stack):
    stack = make_stack(only(quality={"ip": Rule(1, 60)}))
    assert stack.http.post("/v1/public/quality", content=b"x").status_code == 422
    # A header the service does not trust changes nothing.
    reply = stack.http.post(
        "/v1/public/quality", content=b"x", headers={"X-Real-IP": "192.0.2.200"}
    )
    assert refused(reply)


def test_sign_in_and_sign_up_attempts_are_limited(make_stack):
    """Counted before anything else, so even a service without a chain, which signs nobody
    in, counts them; test_sessions.py signs in on a chain."""
    stack = make_stack(only(sign_in={"ip": Rule(4, 600)}, sign_up={"ip": Rule(1, 3600)}))
    sign_up = {"address": "0x" + "11" * 20, "sign_up": {"party": "requester:sim-new"}}
    challenge = {"address": "0x" + "11" * 20}
    assert stack.http.post("/v1/session/challenge", json=sign_up).status_code == 404
    reply = stack.http.post("/v1/session/challenge", json=sign_up)
    assert refused(reply, retry_after=3600) and "(sign_up)" in reply.json()["error"]["message"]
    # The refused sign-up counted against neither limit: three sign-in attempts are left.
    for _ in range(2):
        assert stack.http.post("/v1/session/challenge", json=challenge).status_code == 404
    assert stack.http.post("/v1/session", json={}).status_code == 404  # signing in counts
    reply = stack.http.post("/v1/session", json={})
    assert refused(reply) and "(sign_in)" in reply.json()["error"]["message"]
    # Reading and ending a session are not attempts.
    for _ in range(5):
        assert stack.http.get("/v1/session").json() == {"session": None}
        assert stack.http.delete("/v1/session").status_code != 429


# --------------------------------------------------------------------------- what is kept


def test_counts_keep_no_address_change_no_state_and_expire(make_stack):
    stack = make_stack(only(quality={"ip": Rule(5, 60)}), header="x-real-ip")
    before = stack.version()
    stack.http.post("/v1/public/quality", content=b"x", headers={"X-Real-IP": "192.0.2.77"})
    db = stack.service.storage.db
    rows = db.query("SELECT * FROM rate_limits")
    assert len(rows) == 1 and rows[0]["hits"] == 1
    assert "192.0.2.77" not in json.dumps(rows, default=str)
    assert rows[0]["subject"].startswith("ip:") and len(rows[0]["subject"]) == 3 + 64
    # Counting changes nothing another process keeps in memory: no reload anywhere.
    assert stack.version() == before
    # The next count deletes the counts whose window is over.
    stack.wall.at = START + timedelta(minutes=5)
    stack.http.post("/v1/public/quality", content=b"x", headers={"X-Real-IP": "192.0.2.78"})
    rows = db.query("SELECT * FROM rate_limits")
    assert len(rows) == 1 and rows[0]["window_start"] == int(stack.wall.at.timestamp())


def test_every_process_counts_alike(make_stack):
    """Two processes on one database share the counts (the key for IP addresses too)."""
    one = make_stack(only(quality={"ip": Rule(2, 60)}), header="x-real-ip")
    two = make_stack(only(quality={"ip": Rule(2, 60)}), header="x-real-ip")
    headers = {"X-Real-IP": "192.0.2.5"}
    assert one.http.post("/v1/public/quality", content=b"x", headers=headers).status_code == 422
    assert two.http.post("/v1/public/quality", content=b"x", headers=headers).status_code == 422
    assert refused(one.http.post("/v1/public/quality", content=b"x", headers=headers))


def test_without_limits_nothing_is_counted(make_stack):
    stack = make_stack(None)
    for number in range(1, 26):
        assert stack.create("requester:sim-a", number).status_code == 201
    assert stack.service.storage.db.query("SELECT COUNT(*) AS n FROM rate_limits")[0]["n"] == 0


# --------------------------------------------------------------------------- the body limit


def test_bodies_over_4_mb_are_refused_before_any_route_reads_them(make_stack):
    stack = make_stack(None)
    assert MAX_BODY_BYTES == 4_000_000
    requester = "requester:sim-a"
    exactly = b"x" * MAX_BODY_BYTES
    assert stack.post("/v1/requests", requester, content=exactly).status_code == 422  # read
    reply = stack.post("/v1/requests", requester, content=exactly + b"x")
    assert reply.status_code == 413 and reply.json()["error"]["code"] == "too_large"
    assert reply.headers["content-security-policy"]  # still with the security headers

    def pieces():  # no Content-Length: refused while it arrives
        for _ in range(5):
            yield b"y" * 1_000_000

    reply = stack.http.post(
        "/v1/public/quality", content=pieces(), headers={"Content-Type": "text/plain"}
    )
    assert reply.status_code == 413
    # A body that lies about its length is refused by what it says.
    reply = stack.http.post(
        "/v1/public/quality", content=b"x", headers={"Content-Length": str(MAX_BODY_BYTES + 1)}
    )
    assert reply.status_code == 413


# --------------------------------------------------------------------------- the settings


def test_the_limits_are_settings():
    assert Limits.parse(None).rules == DEFAULTS
    assert Limits.parse("  ").rules == DEFAULTS
    assert Limits.parse("off") is None and Limits.parse("OFF") is None
    changed = Limits.parse('{"quality": {"ip": [60, 3600]}, "upload": {"party": null}}')
    assert changed.rules["quality"]["ip"] == Rule(60, 3600)
    assert changed.rules["upload"]["party"] is None
    assert changed.rules["upload"]["ip"] == DEFAULTS["upload"]["ip"]
    assert changed.rules["sign_in"] == DEFAULTS["sign_in"]
    for bad in (
        "[1, 2]",
        "{",
        '{"nope": {"ip": [1, 2]}}',
        '{"quality": {"host": [1, 2]}}',
        '{"quality": {"ip": [0, 60]}}',
        '{"quality": {"ip": [1]}}',
        '{"quality": {"ip": [true, 60]}}',
        '{"quality": [1, 60]}',
    ):
        with pytest.raises(LimitsError):
            Limits.parse(bad)


def test_the_defaults_are_documented(repo_root):
    api = (repo_root / "docs" / "api.md").read_text(encoding="utf-8")
    for name, subjects in DEFAULTS.items():
        for subject, rule in subjects.items():
            if rule is not None:
                row = f"| `{name}` |"
                assert row in api, name
                assert f"{rule.count} per {rule.seconds} s" in api, (name, subject)


def test_addresses_count_per_host():
    assert network_of("192.0.2.1") == "192.0.2.1"
    assert network_of("::ffff:192.0.2.1") == "192.0.2.1"
    assert network_of("2001:db8::1") == "2001:db8::/64"
    assert network_of("testclient") == "testclient"

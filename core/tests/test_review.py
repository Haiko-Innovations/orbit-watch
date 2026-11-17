"""Findings of the review before the launch (phase 4, step 4.7; decision P4-14), each
with its test: who reads the reasons people write, and the session cookie's name and
lifetime (docs/security-review.md). Everything is SIMULATED."""

import json

from test_api import ACCEPTABLE, REQUESTER, funded_request, new_key, world  # noqa: F401

from orbit_watch.canonical import sha256_bytes

REASON = "SIMULATED: the timing looks off by a second"


def challenged(world):  # noqa: F811
    requester, station = funded_request(world)
    client, clock = world["client"], world["clock"]
    clock.at("2026-11-02T04:00:00Z")
    delivered = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": sha256_bytes(ACCEPTABLE)},
    )
    assert delivered.status_code == 200, delivered.text
    clock.at("2026-11-02T05:00:00Z")
    response = client.call(
        "POST", "/v1/requests/SIM-REQ-0001/challenge", requester, {"reason": REASON}
    )
    assert response.status_code == 200, response.text
    return requester, station


def test_only_the_parties_read_the_reasons_people_write(world):  # noqa: F811
    """ASVS 8.2.2: any signed-in party may follow a request, but a challenge's and the
    reviewers' reasons are for its parties and the administrators until it is published
    (personal-data.md)."""
    requester, station = challenged(world)
    client = world["client"]
    for key in (requester, station, world["admin"]):
        view = client.call("GET", "/v1/requests/SIM-REQ-0001", key).json()
        assert view["record"]["challenge_reason"] == REASON
        assert "reasons_hidden" not in view
    outsider = new_key(world, "station:SIM-OUTSIDER", "station")
    other_requester = new_key(world, "requester:sim-other-team", "requester")
    for key in (outsider, other_requester):
        view = client.call("GET", "/v1/requests/SIM-REQ-0001", key).json()
        assert view["record"]["challenge_reason"] is None
        assert view["record"]["vote_reasons"] == []
        assert view["reasons_hidden"] is True
        assert view["record"]["status"] == "in_review"  # the rest is still there
        assert REASON not in json_text(view)
    assert REQUESTER in json_text(client.call("GET", "/v1/requests", outsider).json())


def json_text(document) -> str:
    return json.dumps(document)

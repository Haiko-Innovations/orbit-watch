"""Station profiles and simulated observations for a station's own reservation (phase 3,
step 3.5, decision D-30). With the points ledger: no chain needed. Everything SIMULATED."""

import json

from helpers import packaged
from test_api import STATION, funded_request, new_key, world  # noqa: F401

from orbit_watch.canonical import sha256_bytes


def put(client, path, key, body):
    put.count += 1
    return client.call("PUT", path, key, body, headers={"Idempotency-Key": f"put-{put.count}"})


put.count = 0


def template(name="sim-cmos-gps"):
    return json.loads(packaged(f"stations/{name}.json"))


def test_the_simulated_templates_are_public(world):  # noqa: F811
    listed = world["client"].call("GET", "/v1/public/station-templates").json()["templates"]
    assert {t["id"] for t in listed} == {
        "sim-azel-mount",
        "sim-clock-offset",
        "sim-cmos-gps",
        "sim-visual-binoculars",
    }
    assert all(t["simulated"] is True for t in listed)


def test_a_station_keeps_its_own_profile(world):  # noqa: F811
    client = world["client"]
    station = new_key(world, STATION, "station")
    other = new_key(world, "station:SIM-OULU", "station")
    path = f"/v1/stations/{STATION}/profile"
    assert client.call("GET", path, station).json()["error"]["code"] == "no_profile"

    broken = put(client, path, station, {"profile": {"format": "nonsense"}})
    assert broken.json()["error"]["code"] == "invalid_profile"
    someone_else = put(client, path, station, {"profile": template("sim-azel-mount")})
    assert someone_else.json()["error"]["code"] == "wrong_station"  # its id is SIM-KUOPIO

    profile = template()  # SIM-ESPOO
    saved = put(client, path, station, {"profile": profile})
    assert saved.status_code == 200, saved.text
    assert client.call("GET", path, station).json()["profile"] == profile
    # The coordinates are personal data: other stations do not see them, admins do.
    assert client.call("GET", path, other).json()["error"]["code"] == "not_yourself"
    assert put(client, path, other, {"profile": profile}).status_code == 403
    assert client.call("GET", path, world["admin"]).status_code == 200


def test_simulated_observations_for_the_own_reservation_pass_verification(world):  # noqa: F811
    client = world["client"]
    _, station = funded_request(world, "SIM-REQ-0001")  # reserved by SIM-ESPOO
    simulate = "/v1/requests/SIM-REQ-0001/simulate"
    assert client.call("POST", simulate, station).json()["error"]["code"] == "no_profile"
    put(client, f"/v1/stations/{STATION}/profile", station, {"profile": template()})

    made = client.call("POST", simulate, station).json()
    assert made["simulated"] is True and made["format"] == "json"
    assert made["file_name"] == "SIM-REQ-0001-SIM-ESPOO-simulated.json"
    body = made["observations"].encode("utf-8")
    assert made["sha256"] == sha256_bytes(body)
    document = json.loads(body)
    assert document["simulated"] is True and document["station"]["id"] == "SIM-ESPOO"
    again = client.call("POST", simulate, station).json()
    assert again["sha256"] != made["sha256"]  # a new draw each time, never a resubmission

    delivered = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=body,
        headers={"Content-SHA256": made["sha256"]},
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["summary"]["automated_verdict"] == "pass"


def test_only_the_reserving_station_simulates(world):  # noqa: F811
    client = world["client"]
    funded_request(world, "SIM-REQ-0001")
    other = new_key(world, "station:SIM-OULU", "station")
    refused = client.call("POST", "/v1/requests/SIM-REQ-0001/simulate", other)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "not_reserved_by_you"


def test_the_reserving_station_reads_the_request_document(world):  # noqa: F811
    """The station needs the request to observe it; other files stay with the parties."""
    client = world["client"]
    requester, station = funded_request(world, "SIM-REQ-0001")  # reserved by SIM-ESPOO
    other = new_key(world, "station:SIM-OULU", "station")
    view = client.call("GET", "/v1/requests/SIM-REQ-0001", requester).json()
    document = view["record"]["terms"]["request_sha256"]
    assert client.call("GET", f"/v1/files/{document}", station).status_code == 200
    # Reserved by someone else: no longer an open invitation.
    assert client.call("GET", f"/v1/files/{document}", other).status_code == 404

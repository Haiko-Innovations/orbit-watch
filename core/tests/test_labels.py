"""Labels of requests whose reports are older than the labels (decision D-52).

A report of format 1.0 (methods 1.0.0 and 2.0.0) names its reference orbit's epoch but not
the set's SHA-256. Production's first settled request has one, and its public page must
still answer. Everything is SIMULATED.
"""

import json

from test_api import ACCEPTABLE, funded_request, world  # noqa: F401

from orbit_watch.canonical import sha256_bytes

# The reference orbit block of a format 1.0 report, as production's first one has it.
OLD_BLOCK = {
    "norad_id": 339001,
    "object_name": "SIM-CUBESAT-A (SIMULATED)",
    "epoch": "2026-11-01T00:00:00.000000",
    "element_set_no": "999",
    "propagator": "SGP4 (sgp4 library via Skyfield)",
}


class OldReports:
    """The service's files, with one report as format 1.0 wrote it."""

    def __init__(self, files, report_sha256):
        self.files, self.report_sha256 = files, report_sha256

    def __getitem__(self, sha256):
        data = self.files[sha256]
        if sha256 != self.report_sha256:
            return data
        report = json.loads(data)
        report["report_format_version"] = "1.0"
        report["reference_orbit"] = OLD_BLOCK
        return json.dumps(report).encode()

    def __contains__(self, sha256):
        return sha256 in self.files

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files)


def test_a_report_of_format_1_0_still_has_its_labels(world, monkeypatch):  # noqa: F811
    _, station = funded_request(world)
    client, service = world["client"], world["service"]
    world["clock"].at("2026-11-02T04:00:00Z")
    delivered = client.call(
        "POST",
        "/v1/requests/SIM-REQ-0001/deliveries",
        station,
        content=ACCEPTABLE,
        headers={"Content-SHA256": sha256_bytes(ACCEPTABLE)},
    )
    assert delivered.status_code == 200, delivered.text
    report_sha256 = service.deliveries["SIM-REQ-0001"].report_sha256
    monkeypatch.setattr(service, "files", OldReports(service.files, report_sha256))

    orbit = service.labels("SIM-REQ-0001")["reference_orbit"]
    assert orbit["epoch"] == "2026-11-01T00:00:00.000000"
    assert orbit["element_set_sha256"] is None and orbit["final"] is True
    assert orbit["source"] == "service" and orbit["simulated"] is True
    view = client.call("GET", "/v1/requests/SIM-REQ-0001", station)
    assert view.status_code == 200, view.text

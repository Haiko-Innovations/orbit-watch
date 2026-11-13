"""The phase 1 demo: outcomes, conservation and byte-identical committed output."""

import json

import pytest

from orbit_watch.sim.phase1_demo import run_phase1_demo


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("phase1")
    return out, run_phase1_demo(out)


def test_every_request_ends_as_designed(demo):
    _, summary = demo
    outcomes = {rid: item["summary"]["outcome"] for rid, item in summary["requests"].items()}
    assert outcomes == {
        "SIM-REQ-1001": "accepted",
        "SIM-REQ-1002": "rejected",
        "SIM-REQ-1003": "rejected",
        "SIM-REQ-1004": "disputed",
        "SIM-REQ-1005": "expired",
    }
    states = {rid: item["publication"]["state"] for rid, item in summary["requests"].items()}
    assert states["SIM-REQ-1004"] == "embargoed"
    assert all(s == "published" for rid, s in states.items() if rid != "SIM-REQ-1004")


def test_points_are_conserved(demo):
    _, summary = demo
    assert summary["escrow_total"] == 0
    assert sum(summary["balances"].values()) == 1000  # the only grant


def test_the_rubber_stamper_is_visible(demo):
    _, summary = demo
    profile = summary["reviewer_profiles"]["reviewer:sim-aino"]
    assert profile["votes"]["approval_rate"] == 1.0
    assert profile["calibration"]["correct"] < profile["calibration"]["answered"]


def test_committed_output_is_up_to_date(demo, examples_dir):
    out, _ = demo
    committed = examples_dir / "phase1"
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(p.name for p in committed.iterdir())
    for name in names:
        assert (out / name).read_bytes() == (committed / name).read_bytes(), name
    assert json.loads((committed / "summary.json").read_text())["notice"].startswith("SIMULATED")


def test_the_deliveries_name_no_version_so_releases_draw_the_same_rounds():
    from orbit_watch.catalog import parse_catalog
    from orbit_watch.sim.phase1_demo import _deliveries, _packaged

    for data in _deliveries(parse_catalog(_packaged("catalog.json"))).values():
        assert json.loads(data)["source"]["software"] == "orbit-watch simulator"

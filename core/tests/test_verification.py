import json
import os
import subprocess
import sys

import pytest
from helpers import catalog_bytes, policy_bytes, request_bytes

from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.formats import iod, owjson
from orbit_watch.formats.sites import Sites
from orbit_watch.model import Station
from orbit_watch.sim.scenarios import SCENARIOS, run_demo
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc
from orbit_watch.verify.engine import CHECK_ORDER, UsageError, VerificationInput, verify


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    return out, {r["dataset"]: r for r in run_demo(out)}


@pytest.fixture(scope="module")
def acceptable(demo):
    out, _ = demo
    return (out / "datasets" / "acceptable" / "observations.json").read_bytes()


def run(observations, previous=(), declared=None, **request_changes):
    return verify(
        VerificationInput(
            request=request_bytes(**request_changes),
            observations=observations,
            catalog=catalog_bytes(),
            policy=policy_bytes(),
            previous=list(previous),
            declared_sha256=declared,
        )
    )


def results(report):
    return {c["id"]: c["result"] for c in report["checks"]}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_every_dataset_gets_the_expected_result(demo, scenario):
    out, by_name = demo
    result = by_name[scenario.name]
    assert result["verdict"] == scenario.expected_verdict
    assert result["failed_checks"] == scenario.expected_failures
    report = json.loads((out / "datasets" / scenario.name / "report.json").read_text())
    assert [c["id"] for c in report["checks"]] == CHECK_ORDER
    assert report["simulated_input"] is True and "SIMULATED" in report["notice"]
    for check in report["checks"]:
        assert check["reason"].endswith(".") and len(check["reason"]) > 20


def test_explanations_name_the_cause(demo):
    out, _ = demo

    def reason(name, check_id):
        report = json.loads((out / "datasets" / name / "report.json").read_text())
        return next(c["reason"] for c in report["checks"] if c["id"] == check_id)

    assert "'time' is a required property" in reason("invalid", "format")
    assert "after the window closed" in reason("late", "time_window")
    assert "already appear in an earlier delivery" in reason("duplicate", "duplicates")
    assert "behind the prediction" in reason("wrong_target", "orbit_residuals")
    assert "too imprecise" in reason("too_imprecise", "declared_uncertainty")


def test_committed_examples_are_up_to_date(demo, examples_dir):
    """examples/simulated is the output of `orbit-watch demo`, byte for byte."""
    out, _ = demo
    committed = examples_dir / "simulated"
    generated = sorted(p.relative_to(out) for p in out.rglob("*") if p.is_file())
    assert generated == sorted(
        p.relative_to(committed) for p in committed.rglob("*") if p.is_file()
    )
    for relative in generated:
        assert (out / relative).read_bytes() == (committed / relative).read_bytes(), relative


def test_report_is_byte_identical_across_processes(tmp_path):
    """Same input, byte-identical report, also with different hash seeds."""
    script = "import sys; from orbit_watch.sim.scenarios import run_demo; run_demo(sys.argv[1])"
    outputs = []
    for seed in ("1", "12345"):
        target = tmp_path / seed
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run([sys.executable, "-c", script, str(target)], check=True, env=env)
        outputs.append(target)
    for report in outputs[0].rglob("report.json"):
        twin = outputs[1] / report.relative_to(outputs[0])
        assert report.read_bytes() == twin.read_bytes()


def test_hash_mismatch(acceptable):
    report = run(acceptable, declared="0" * 64)
    assert results(report)["hash_match"] == "fail"
    assert results(run(acceptable, declared=sha256_bytes(acceptable)))["hash_match"] == "pass"
    assert results(run(acceptable))["hash_match"] == "skip"


def test_target_not_on_allow_list(acceptable):
    report = run(acceptable, norad_id=339009)
    assert results(report)["target_allowed"] == "fail"
    assert "civilian" in next(c["reason"] for c in report["checks"] if c["id"] == "target_allowed")
    assert results(report)["target_match"] == "fail"


def test_simulated_data_cannot_fulfil_a_real_request(acceptable):
    report = run(acceptable, simulated=False)
    assert results(report)["simulation_label"] == "fail"
    assert report["verdict"] == "fail"


def test_stale_reference_orbit_is_inconclusive():
    profile = load_profile("sim-cmos-gps")
    from orbit_watch.catalog import parse_catalog

    later = simulate(
        parse_catalog(catalog_bytes()),
        339001,
        profile,
        parse_utc("2026-11-11T00:00:00Z"),
        parse_utc("2026-11-12T00:00:00Z"),
        seed=1,
    )
    data = owjson.write_observation_set(later).encode()
    report = run(data, start="2026-11-11T00:00:00Z", end="2026-11-12T00:00:00Z")
    assert results(report)["orbit_residuals"] == "inconclusive"
    assert report["verdict"] == "inconclusive"


def test_target_missing_from_catalog_is_inconclusive(acceptable):
    document = json.loads(catalog_bytes())
    document["records"] = [r for r in document["records"] if r["NORAD_CAT_ID"] != 339001]
    report = verify(
        VerificationInput(
            request=request_bytes(),
            observations=acceptable,
            catalog=json.dumps(document).encode(),
            policy=policy_bytes(),
        )
    )
    assert results(report)["orbit_residuals"] == "inconclusive"


def test_internal_duplicates(acceptable):
    document = json.loads(acceptable)
    document["observations"].append(document["observations"][0])
    report = run(dumps_pretty(document, sort_keys=False).encode())
    assert results(report)["duplicates"] == "fail"


def test_identical_file_resubmitted(acceptable):
    report = run(acceptable, previous=[acceptable])
    reason = next(c["reason"] for c in report["checks"] if c["id"] == "duplicates")
    assert "identical file" in reason


def test_iod_delivery_with_sites(acceptable):
    obs_set = owjson.read_observation_set(acceptable)
    text = iod.write_iod([obs_set]).encode()
    station = obs_set.station
    sites = Sites(
        [
            Station(
                station.id,
                station.latitude_deg,
                station.longitude_deg,
                station.altitude_m,
                iod_station_number=station.iod_station_number,
            )
        ]
    )
    report = verify(
        VerificationInput(
            request=request_bytes(),
            observations=text,
            catalog=catalog_bytes(),
            policy=policy_bytes(),
            sites=sites,
        )
    )
    assert report["inputs"]["observations_format"] == "iod"
    assert report["verdict"] == "pass", [c for c in report["checks"] if c["result"] != "pass"]


def test_multiple_groups_rejected():
    text = (
        b"23456 26 901A   9901 G 20261101170210000 16 25 2004938+415259 17\n"
        b"23457 26 901B   9901 G 20261101170310000 16 25 2004938+415259 17\n"
    )
    sites = Sites([Station("SIM-X", 60.0, 25.0, 10.0, iod_station_number=9901)])
    report = verify(
        VerificationInput(
            request=request_bytes(),
            observations=text,
            catalog=catalog_bytes(),
            policy=policy_bytes(),
            sites=sites,
        )
    )
    assert results(report)["format"] == "fail"
    assert "exactly one" in report["checks"][0]["reason"]


def test_invalid_inputs_to_the_verifier_are_usage_errors(acceptable):
    with pytest.raises(UsageError):
        verify(
            VerificationInput(
                request=b"{}",
                observations=acceptable,
                catalog=catalog_bytes(),
                policy=policy_bytes(),
            )
        )
    with pytest.raises(UsageError):
        verify(
            VerificationInput(
                request=request_bytes(),
                observations=acceptable,
                catalog=b"[]",
                policy=policy_bytes(),
            )
        )
    with pytest.raises(UsageError):
        run(acceptable, start="2026-11-03T00:00:00Z")  # window ends before it starts

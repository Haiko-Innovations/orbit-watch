"""Reference orbits in the core (phase 5, step 5.1; decisions P5-02 to P5-05).

No test here calls an outside service. The answers of CelesTrak and SatChecker are stand-ins
built from the SIMULATED catalogue, since real element sets are never committed (D-06). The
tests at the end use real element sets from the local cache, and are skipped without it.
"""

import copy
import gzip
import io
import json
import urllib.error
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from helpers import catalog_bytes, policy_bytes, request_bytes
from sgp4 import exporter, omm
from sgp4.api import Satrec
from skyfield.api import EarthSatellite

from orbit_watch import orbit_cache
from orbit_watch.catalog import CatalogError, parse_catalog, record_sha256, timescale
from orbit_watch.cli import main
from orbit_watch.fetch import FetchError, build_url, fetch_gp
from orbit_watch.formats import owjson
from orbit_watch.lifecycle import Terms
from orbit_watch.quality import score_station
from orbit_watch.satchecker import (
    PAUSE_S,
    SatCheckerError,
    fetch_nearest,
    nearest_url,
    parse_answer,
    tle_sha256,
)
from orbit_watch.sim.simulator import load_profile, simulate
from orbit_watch.timeutil import parse_utc
from orbit_watch.verify.engine import METHOD_NAME, METHOD_VERSION, VerificationInput, verify

SIM = json.loads(catalog_bytes())["records"][0]  # SIM-CUBESAT-A, 339001, epoch 2026-11-01


def catalogue(*records, simulated=False) -> bytes:
    return json.dumps(
        {"format": "orbit-watch/gp-catalog", "simulated": simulated, "records": list(records)}
    ).encode()


def moved(epoch: str, element_set_no: int = 998) -> dict:
    """The SIMULATED set with another epoch: a different orbit, for choosing between sets."""
    record = copy.deepcopy(SIM)
    record["EPOCH"], record["ELEMENT_SET_NO"] = epoch, element_set_no
    return record


def observations(start: str, end: str) -> bytes:
    observed = simulate(
        parse_catalog(catalog_bytes()),
        339001,
        load_profile("sim-cmos-gps"),
        parse_utc(start),
        parse_utc(end),
        seed=1,
    )
    return owjson.write_observation_set(observed).encode()


EARLY = {"start": "2026-11-01T15:00:00Z", "end": "2026-11-02T03:00:00Z"}
LATER = {"start": "2026-11-18T00:00:00Z", "end": "2026-11-19T00:00:00Z"}


def run(window, catalog):
    return verify(
        VerificationInput(
            request=request_bytes(**window),
            observations=observations(window["start"], window["end"]),
            catalog=catalog,
            policy=policy_bytes(),
        )
    )


def residuals(report):
    return next(c for c in report["checks"] if c["id"] == "orbit_residuals")


# The catalogue ----------------------------------------------------------------------------


def test_a_catalogue_keeps_every_set_and_names_the_newest():
    catalog = parse_catalog(catalogue(SIM, moved("2026-11-20T00:00:00.000000"), SIM))
    assert len(catalog.sets[339001]) == 2  # the same set twice is one set
    assert catalog.record(339001)["EPOCH"].startswith("2026-11-20")
    sets = catalog.element_sets(339001)
    assert [s.epoch.day for s in sets] == [1, 20]


def test_the_nearest_set_and_a_tie():
    catalog = parse_catalog(
        catalogue(
            moved("2026-11-10T00:00:00.000000", 997), SIM, moved("2026-11-19T00:00:00.000000")
        )
    )
    near = catalog.nearest(339001, datetime(2026, 11, 3, tzinfo=UTC))
    assert near.epoch.day == 1 and near.sha256 == record_sha256(SIM)
    assert catalog.nearest(339001, datetime(2026, 11, 18, tzinfo=UTC)).epoch.day == 19
    tie = catalog.nearest(339001, datetime(2026, 11, 5, 12, tzinfo=UTC))
    assert tie.epoch.day == 1  # 4.5 days either way: the earlier set


def test_a_source_is_not_an_omm_field():
    record = dict(SIM, source={"service": "a stand-in"})
    catalog = parse_catalog(catalogue(record))
    element_set = catalog.nearest(339001, datetime(2026, 11, 1, tzinfo=UTC))
    assert element_set.sha256 == record_sha256(SIM)
    assert element_set.source == {"service": "a stand-in"}
    with pytest.raises(CatalogError, match="source is not an object"):
        parse_catalog(catalogue(dict(SIM, source="CelesTrak")))


# Verification and the quality meter -------------------------------------------------------


def test_verification_uses_the_set_nearest_the_observations():
    # Method 2.0.0 used the newest set, 18 days from these observations: inconclusive.
    report = run(EARLY, catalogue(SIM, moved("2026-11-20T00:00:00.000000")))
    assert residuals(report)["result"] == "pass"
    reference = report["reference_orbit"]
    assert reference["epoch"] == SIM["EPOCH"]
    assert reference["element_set_sha256"] == record_sha256(SIM)
    assert reference["selection"] == "nearest the middle of the observations"
    assert reference["element_sets_in_catalogue"] == 2
    assert report["method"]["version"] == METHOD_VERSION == "2.1.0"
    assert report["report_format_version"] == "1.1"


def test_a_later_delivery_gets_the_later_set():
    report = run(LATER, catalogue(SIM, moved("2026-11-18T12:00:00.000000")))
    assert report["reference_orbit"]["epoch"].startswith("2026-11-18")
    # The moved set is another orbit, so the observations do not follow it.
    assert residuals(report)["result"] == "fail"


def test_the_age_limit_names_the_nearest_set():
    report = run(LATER, catalogue(SIM, moved("2026-11-05T00:00:00.000000")))
    check = residuals(report)
    assert check["result"] == "inconclusive"
    assert check["reason"].startswith("The nearest reference orbit epoch (2026-11-05 00:00 UTC)")


def test_a_report_names_the_source_but_not_the_set():
    nearest = parse_answer(tle_answer(), 339001, "tle", endpoint="get-nearest-tle")
    report = run(EARLY, catalogue(nearest.record))
    source = report["reference_orbit"]["source"]
    assert source["service"] == "IAU CPS SatChecker"
    assert source["original_sha256"] == nearest.sha256
    assert "tle_line1" not in source and "tle_line2" not in source
    assert sim_tle()[0] not in json.dumps(report)


def test_one_set_per_object_gives_the_same_verdict_as_before():
    report = run(EARLY, catalog_bytes())
    assert report["verdict"] == "pass"
    assert report["reference_orbit"]["element_sets_in_catalogue"] == 1


def test_the_quality_meter_uses_the_nearest_set():
    observed = owjson.read_observation_set(observations(EARLY["start"], EARLY["end"]))
    catalog = parse_catalog(catalogue(SIM, moved("2026-11-20T00:00:00.000000")))
    report = score_station([observed], catalog)
    assert report["method_version"] == "1.1.0"
    assert report["overall"]["observations"] > 0
    assert not any("more than" in n for n in report.get("notices", []))


def test_the_terms_name_the_method():
    default = next(f.default for f in fields(Terms) if f.name == "verification_method")
    assert default == f"{METHOD_NAME} {METHOD_VERSION}"


# CelesTrak (fetch-gp) ---------------------------------------------------------------------


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def sim_csv() -> bytes:
    fields = [k for k in SIM]
    lines = [",".join(fields), ",".join(str(SIM[k]) for k in fields)]
    return ("\n".join(lines) + "\n").encode()


def test_fetch_gp_asks_for_compressed_csv(tmp_path):
    assert build_url("CATNR", "25544").endswith("CATNR=25544&FORMAT=csv")
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(gzip.compress(sim_csv()), headers={"Content-Encoding": "gzip"})

    message = fetch_gp("CATNR", "339001", tmp_path / "gp.csv", opener=opener)
    assert "1 element set(s)" in message
    assert calls[0].get_header("Accept-encoding") == "gzip"
    assert (tmp_path / "gp.csv").read_bytes() == sim_csv()  # saved decompressed
    assert parse_catalog((tmp_path / "gp.csv").read_bytes()).record(339001)["EPOCH"]


def test_fetch_gp_reads_an_answer_that_is_not_compressed(tmp_path):
    fetch_gp(
        "CATNR", "339001", tmp_path / "gp.csv", opener=lambda r, timeout: FakeResponse(sim_csv())
    )
    assert (tmp_path / "gp.csv").read_bytes() == sim_csv()


@pytest.mark.parametrize(
    ("status", "advice"),
    [
        (404, "do not ask for it again"),
        (503, "at least 15 minutes"),
        (500, "at least 15 minutes"),
        (403, "read its message"),
    ],
)
def test_fetch_gp_stops_and_says_what_the_policy_asks(tmp_path, status, advice):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, status, "", {}, io.BytesIO(b"No"))

    with pytest.raises(FetchError, match=advice):
        fetch_gp("CATNR", "1", tmp_path / "gp.csv", opener=opener)
    assert len(calls) == 1 and not (tmp_path / "gp.csv").exists()


# SatChecker -------------------------------------------------------------------------------


def sim_tle() -> tuple[str, str]:
    satrec = Satrec()
    omm.initialize(satrec, {k: str(v) for k, v in SIM.items()})
    return exporter.export_tle(satrec)


def tle_answer(line1=None, line2=None, sets=1) -> bytes:
    l1, l2 = sim_tle()
    item = {
        "data_source": "a stand-in",
        "date_collected": "2026-11-01 01:00:00 UTC",
        "epoch": "2026-11-01 00:00:00 UTC",
        "satellite_id": 339001,
        "satellite_name": "SIM-CUBESAT-A (SIMULATED)",
        "tle_line1": line1 or l1,
        "tle_line2": line2 or l2,
    }
    return json.dumps(
        [{"orbital_data": [item] * sets, "source": "IAU CPS SatChecker", "version": "1.9.0"}]
    ).encode()


def omm_answer() -> bytes:
    item = {"satellite_id": 339001, "orbital_elements": SIM, "data_source": "a stand-in"}
    return json.dumps([{"orbital_data": [item], "version": "1.9.0"}]).encode()


def test_nearest_url():
    url = nearest_url("tle", 59588, datetime(2024, 9, 1, 12, tzinfo=UTC))
    assert url == (
        "https://satchecker.cps.iau.org/tools/get-nearest-tle/"
        "?id=59588&id_type=catalog&epoch=2460555.00000000"
    )
    with pytest.raises(ValueError):
        nearest_url("xml", 1, datetime(2024, 9, 1, tzinfo=UTC))


def test_a_tle_becomes_an_omm_record_with_its_source():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(tle_answer())

    nearest = fetch_nearest(339001, datetime(2026, 11, 1, tzinfo=UTC), opener=opener)
    assert len(calls) == 1 and calls[0].get_header("User-agent").startswith("orbit-watch/")
    assert nearest.sha256 == tle_sha256(*sim_tle())
    assert nearest.record["source"]["service"] == "IAU CPS SatChecker"
    assert nearest.record["source"]["original_sha256"] == nearest.sha256
    # The OMM record gives the TLE's orbit, to a metre.
    from_omm = parse_catalog(catalogue(nearest.record)).satellite(339001)
    from_tle = EarthSatellite(*sim_tle(), "", timescale())
    t = timescale().utc(2026, 11, 1, 12)
    assert np.linalg.norm(from_omm.at(t).position.km - from_tle.at(t).position.km) < 0.001


def test_an_omm_answer():
    nearest = parse_answer(omm_answer(), 339001, "omm", endpoint="get-nearest-omm")
    assert nearest.record["EPOCH"] == SIM["EPOCH"] and nearest.kind == "omm"


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        (b"<html>", "not the expected JSON"),
        (tle_answer(sets=0), "0 element sets"),
        (tle_answer(sets=2), "2 element sets"),
    ],
)
def test_an_unexpected_answer_stops(body, problem):
    with pytest.raises(SatCheckerError, match=problem):
        parse_answer(body, 339001, "tle", endpoint="get-nearest-tle")


def test_another_object_is_refused():
    with pytest.raises(SatCheckerError, match="of object 339001, not 25544"):
        parse_answer(tle_answer(), 25544, "tle", endpoint="get-nearest-tle")


def test_an_error_answer_is_not_retried():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 503, "", {}, io.BytesIO(b"busy"))

    with pytest.raises(SatCheckerError, match="HTTP 503") as error:
        fetch_nearest(339001, datetime(2026, 11, 1, tzinfo=UTC), opener=opener)
    assert error.value.status == 503 and len(calls) == 1


# The manifest and the cache ---------------------------------------------------------------


def manifest_of(*answers) -> orbit_cache.Manifest:
    manifest = orbit_cache.Manifest([], "stand-ins")
    for body in answers:
        manifest.add(parse_answer(body, 339001, "tle", endpoint="get-nearest-tle"))
    return manifest


def other_answer() -> bytes:
    """Another stand-in set of the object, a day later."""
    later = moved("2026-11-02T00:00:00.000000", 997)
    satrec = Satrec()
    omm.initialize(satrec, {k: str(v) for k, v in later.items()})
    return tle_answer(*exporter.export_tle(satrec))


def test_fill_fetches_what_is_missing_two_seconds_apart(tmp_path):
    manifest = manifest_of(tle_answer(), other_answer())
    answers = {0: tle_answer(), 1: other_answer()}
    calls, pauses = [], []

    def opener(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(answers[len(calls) - 1])

    fetched, present = orbit_cache.fill(
        manifest.entries, tmp_path, opener=opener, sleep=pauses.append
    )
    assert (fetched, present) == (2, 0) and pauses == [PAUSE_S]
    assert orbit_cache.fill(manifest.entries, tmp_path, opener=opener) == (0, 2)
    assert len(calls) == 2
    document = json.loads(orbit_cache.catalog_from_cache(manifest, tmp_path))
    assert document["simulated"] is False and len(document["records"]) == 2
    assert len(parse_catalog(json.dumps(document).encode()).sets[339001]) == 2


def test_fill_stops_at_the_first_error(tmp_path):
    manifest = manifest_of(tle_answer(), other_answer())
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 500, "", {}, io.BytesIO(b""))

    with pytest.raises(SatCheckerError):
        orbit_cache.fill(manifest.entries, tmp_path, opener=opener, sleep=lambda s: None)
    assert len(calls) == 1


def test_fill_refuses_a_set_the_manifest_does_not_name(tmp_path):
    manifest = manifest_of(tle_answer())
    with pytest.raises(orbit_cache.CacheError, match="not the one the manifest names"):
        orbit_cache.fill(
            manifest.entries, tmp_path, opener=lambda r, timeout: FakeResponse(other_answer())
        )
    assert orbit_cache.missing(manifest, tmp_path) == manifest.entries


def test_a_changed_cache_file_is_refused(tmp_path):
    manifest = manifest_of(tle_answer())
    entry = manifest.entries[0]
    path = orbit_cache.cache_file(tmp_path, entry)
    path.parent.mkdir(parents=True)
    path.write_bytes(other_answer())
    with pytest.raises(orbit_cache.CacheError, match="does not hold"):
        orbit_cache.catalog_from_cache(manifest, tmp_path)


def test_a_manifest_round_trip_and_its_checks(tmp_path):
    manifest = manifest_of(other_answer(), tle_answer(), tle_answer())
    assert len(manifest.entries) == 2
    path = tmp_path / "orbits.json"
    orbit_cache.write_manifest(path, manifest)
    again = orbit_cache.parse_manifest(path.read_bytes())
    assert [e.epoch for e in again.entries] == sorted(e.epoch for e in manifest.entries)
    document = json.loads(path.read_text())
    document["element_sets"][0]["kind"] = "xml"
    with pytest.raises(orbit_cache.CacheError, match="unknown kind"):
        orbit_cache.parse_manifest(json.dumps(document).encode())
    with pytest.raises(orbit_cache.CacheError, match="not an orbit-watch/reference-orbits"):
        orbit_cache.parse_manifest(b'{"format": "something else"}')


def test_the_cache_lives_outside_the_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIT_WATCH_CACHE", str(tmp_path / "here"))
    assert orbit_cache.default_cache_dir() == tmp_path / "here"
    monkeypatch.delenv("ORBIT_WATCH_CACHE")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert orbit_cache.default_cache_dir() == tmp_path / "xdg" / "orbit-watch"


def test_the_commands(tmp_path, monkeypatch, capsys):
    from orbit_watch import satchecker

    monkeypatch.setattr(
        satchecker,
        "fetch_nearest",
        lambda norad, when, kind, opener=None: parse_answer(
            tle_answer(), norad, kind, endpoint="get-nearest-tle"
        ),
    )
    cache, manifest = tmp_path / "cache", tmp_path / "orbits.json"
    one = str(tmp_path / "one.json")
    args = ["--catnr", "339001", "--near", "2026-11-01T12:00:00Z", "-o", one]
    assert (
        main(["fetch-satchecker", *args, "--manifest", str(manifest), "--cache", str(cache)]) == 0
    )
    assert "IAU CPS" in capsys.readouterr().out
    out = tmp_path / "catalog.json"
    # Everything is cached, so fetch-orbits makes no request.
    assert main(["fetch-orbits", str(manifest), "--cache", str(cache), "-o", str(out)]) == 0
    assert "0 element set(s) fetched, 1 already" in capsys.readouterr().out
    assert parse_catalog(out.read_bytes()).sets[339001][0]["source"]["data_source"] == "a stand-in"


# Real element sets, from the local cache --------------------------------------------------

REAL = orbit_cache.parse_manifest(
    (Path(__file__).parent / "data" / "reference-orbits.json").read_bytes()
)
needs_cache = pytest.mark.skipif(
    bool(orbit_cache.missing(REAL, orbit_cache.default_cache_dir())),
    reason="real element sets not in the cache: run orbit-watch fetch-orbits "
    "tests/data/reference-orbits.json",
)


@needs_cache
def test_real_sets_from_the_cache():
    catalog = parse_catalog(orbit_cache.catalog_from_cache(REAL, orbit_cache.default_cache_dir()))
    assert len(catalog.sets[58296]) == 3 and len(catalog.sets[59588]) == 1
    # PELICAN 3001 observed in SCORE on 2024-05-20 at about 21 UTC: the set of 05-21 05 UTC.
    nearest = catalog.nearest(58296, datetime(2024, 5, 20, 21, tzinfo=UTC))
    assert nearest.epoch.strftime("%Y-%m-%d") == "2024-05-21"
    assert catalog.record(58296)["EPOCH"].startswith("2024-06-06")


@needs_cache
def test_real_tles_and_their_omm_records_give_the_same_orbit():
    cache = orbit_cache.default_cache_dir()
    ts = timescale()
    for entry in REAL.entries:
        nearest = orbit_cache.cached(cache, entry)
        source = nearest.record["source"]
        from_tle = EarthSatellite(source["tle_line1"], source["tle_line2"], "", ts)
        from_omm = parse_catalog(catalogue(nearest.record)).satellite(entry.norad_id)
        for days in (-1.0, 0.0, 2.0):
            t = ts.tt_jd(from_tle.epoch.tt + days)
            difference = from_tle.at(t).position.km - from_omm.at(t).position.km
            assert np.linalg.norm(difference) < 0.001  # a metre

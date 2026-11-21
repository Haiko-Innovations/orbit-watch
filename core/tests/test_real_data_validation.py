"""The method measured on real data (phase 5, step 5.3; decision D-46).

The committed files are checked offline: the validation set, its credits, the results
and the tables of docs/real-data-validation.md that show them. The measurement itself
runs against the real element sets the manifests name, and those tests are skipped
without the local cache (decision P5-05). The functions are also tested on a SIMULATED
track, which needs no cache.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from orbit_watch import calibration, orbit_cache, score, validation
from orbit_watch.allowlist import DEFAULT_EXCLUDED_NAME_PATTERNS
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.cli import main
from orbit_watch.formats import owjson

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "validation" / "real"
EXAMPLE = ROOT / "examples" / "real"
FILES = sorted((VALIDATION / "observations").glob("*.json"))
SETS = {path.name: owjson.read_observation_set(path.read_bytes()) for path in FILES}
RESULTS = json.loads((VALIDATION / "results.json").read_text())
KNOWN = json.loads((VALIDATION / "known-answers.json").read_text())
PAGE = ROOT / "docs" / "real-data-validation.md"


# The committed files ----------------------------------------------------------------------


def test_the_validation_set_is_real_and_names_its_source():
    assert len(FILES) >= 30
    for path in FILES:
        document = json.loads(path.read_text())
        assert document["format_version"] == "1.1" and document["simulated"] is False
        origin = document["source"]["origin"]
        assert origin["licence"] == "CC-BY-4.0" and origin["observers"]
        assert len(origin["observation_ids"]) == len(document["observations"])
        assert document["source"]["converted_from"] == "score"


def test_only_civilian_objects():
    patterns = [re.compile(p, re.IGNORECASE) for p in DEFAULT_EXCLUDED_NAME_PATTERNS]
    for observation_set in SETS.values():
        name = observation_set.target.name or ""
        assert not any(p.search(name) for p in patterns), name
        assert not name.startswith(("OBJECT ", "SHIJIAN", "OPS ", "CSG-")), name


@pytest.mark.parametrize("directory", [EXAMPLE, VALIDATION], ids=["examples", "validation"])
def test_the_credits_are_what_the_converter_writes(directory):
    paths = sorted((directory / "observations").glob("*.json"))
    sets = [owjson.read_observation_set(p.read_bytes()) for p in paths]
    assert (directory / "CREDITS.md").read_text() == score.credits_markdown(sets)


def test_no_real_element_set_is_committed():
    for path in [*VALIDATION.rglob("*"), PAGE]:
        if path.is_file():
            text = path.read_text()
            assert "tle_line" not in text and "MEAN_MOTION" not in text, path


def test_the_windows_and_the_tracks_not_fetched():
    tracks = json.loads((VALIDATION / "tracks.json").read_text())
    objects = {s.target.norad_id for s in SETS.values()}
    assert {w["norad_id"] for w in tracks["windows"]} == objects
    assert all(n["norad_id"] not in objects and n["why"] for n in tracks["not_fetched"])


def test_the_manifest_names_a_set_for_every_new_object():
    manifest = orbit_cache.parse_manifest((VALIDATION / "reference-orbits.json").read_bytes())
    assert {s.target.norad_id for s in SETS.values()} <= {e.norad_id for e in manifest.entries}


def test_the_results_name_every_input_by_its_hash():
    named = {(f["group"], f["file"]): f["sha256"] for f in RESULTS["inputs"]["observation_files"]}
    on_disk = {
        (group, path.name): sha256_bytes(path.read_bytes())
        for group, directory in (("examples/real", EXAMPLE), ("validation/real", VALIDATION))
        for path in (directory / "observations").glob("*.json")
    }
    assert named == on_disk
    sets = set()
    for directory in (EXAMPLE, VALIDATION):
        manifest = orbit_cache.parse_manifest((directory / "reference-orbits.json").read_bytes())
        sets |= {e.sha256 for e in manifest.entries}
    assert {e["sha256"] for e in RESULTS["inputs"]["element_sets"]} == sets
    assert RESULTS["method"]["version"] == validation.METHOD_VERSION
    assert RESULTS["simulated"] is False


def test_the_page_shows_the_committed_results():
    text = PAGE.read_text()
    assert validation.update_document(text, validation.tables(RESULTS)) == text


def test_the_known_answers_follow_from_the_results():
    assert json.loads(dumps_pretty(validation.known_answers(RESULTS))) == KNOWN
    answers = {e["expected"] for e in KNOWN["entries"]}
    assert answers == {"approve", "reject"}
    for entry in KNOWN["entries"]:
        path = ROOT / entry["group"] / "observations" / entry["file"]
        assert sha256_bytes(path.read_bytes()) == entry["sha256"]
        assert not entry["file"].endswith("77d01109b5d1.json")  # no DECam: not settled
        assert entry["automated_verdict"] == ("pass" if entry["expected"] == "approve" else "fail")


# The functions, on a SIMULATED track ------------------------------------------------------

SIMULATED = ROOT / "examples" / "simulated"


@pytest.fixture(scope="module")
def simulated_inputs():
    data = (SIMULATED / "datasets" / "acceptable" / "observations.json").read_bytes()
    track = validation.Track(
        "simulated", "observations.json", sha256_bytes(data), owjson.read_observation_set(data)
    )
    records = {}
    for record in json.loads((SIMULATED / "catalog.json").read_text())["records"]:
        records.setdefault(int(record["NORAD_CAT_ID"]), []).append(record)
    return validation.Inputs([track], records, [])


def test_a_good_track_and_its_faults(simulated_inputs):
    (row,) = validation.measure(simulated_inputs)["tracks"]
    assert row["result"] == "pass" and row["faults_on"] == "as published"
    faults = row["faults"]
    assert faults["time_shift_s"]["30"] == "fail"
    assert faults["station_moved_km"]["100"] == "fail"
    assert faults["fabricated"] == "pass"
    assert faults["wrong_object"] and set(faults["wrong_object"].values()) == {"fail"}
    assert row["rounded"]["result"] == "pass"
    terms = row["limit_terms"]
    assert terms["orbit_share_of_limit"] > 0.5 and terms["orbit_term_arcsec"] > 0
    # The catalogue's one set is 0.85 days before the track: it stands for "about 1 day".
    assert [a["asked_days"] for a in row["reference_age"]] == [1.0]


def test_a_track_with_a_clock_offset_is_diagnosed(simulated_inputs):
    (track,) = simulated_inputs.tracks
    late = replace(track, observation_set=validation.shifted(track.observation_set, -3.0))
    (row,) = validation.measure(replace(simulated_inputs, tracks=[late]))["tracks"]
    assert row["result"] == "fail"
    assert row["offset_removed"]["result"] == "pass"
    # Stamped 3 s early, the object is 3 s ahead of the prediction: +3 s takes it out.
    assert 2.8 < row["offset_removed"]["shift_s"] < 3.2
    assert row["faults_on"] == "offset removed"


def test_the_changes_change_only_what_they_say(simulated_inputs):
    observation_set = simulated_inputs.tracks[0].observation_set
    first = observation_set.observations[0]
    later = validation.shifted(observation_set, 2.0).observations[0]
    assert (later.time - first.time).total_seconds() == 2.0
    moved = validation.moved(observation_set, 11.132)
    assert moved.station.latitude_deg == pytest.approx(observation_set.station.latitude_deg + 0.1)
    assert moved.observations == observation_set.observations
    rounded = validation.rounded(observation_set, 2)
    assert rounded.station.longitude_deg == round(observation_set.station.longitude_deg, 2)
    other = validation.relabelled(observation_set, 339002, "SIM-CUBESAT-B")
    assert other.target.norad_id == 339002 and other.observations == observation_set.observations
    wider = validation.with_angle_uncertainty(observation_set, 120.0)
    assert {o.angle_uncertainty_arcsec for o in wider.observations} == {120.0}


def test_orbits_and_instruments_are_named():
    assert validation.orbit_class({"MEAN_MOTION": "15.2", "ECCENTRICITY": "0.001"}) == "LEO"
    assert validation.orbit_class({"MEAN_MOTION": "1.0027", "ECCENTRICITY": "0.0002"}) == "GEO"
    assert validation.orbit_class({"MEAN_MOTION": "2.006", "ECCENTRICITY": "0.7"}) == "HEO"
    assert validation.orbit_class({"MEAN_MOTION": "1.7", "ECCENTRICITY": "0.0004"}) == "MEO"
    kind = validation.instrument_kind
    assert kind("WATEC 902H2 Supreme + 1.2/85 mm") == "Video camera (WATEC 902H2)"
    assert kind("Apple iPhone 12 Mini") == kind("iPhone 12 Mini") == "Phone (iPhone 12 Mini)"
    assert kind("Apple iPhone 17 Pro") == "Phone (iPhone 17 Pro)"
    assert kind("eVscope v2.0") == "eVscope" and kind("DECam") == "DECam (Blanco 4 m)"


def test_every_table_needs_its_place_on_the_page():
    tables = {"one": "| a |", "two": "| b |"}
    page = "x\n<!-- measured:one -->\nold\n<!-- /measured:one -->\n"
    with pytest.raises(ValueError, match="no place for the tables two"):
        validation.update_document(page, tables)
    page += "<!-- measured:two -->\n<!-- /measured:two -->\n"
    updated = validation.update_document(page, tables)
    assert "old" not in updated and "| a |\n<!-- /measured:one -->" in updated
    page += "<!-- measured:three -->\n<!-- /measured:three -->\n"
    with pytest.raises(ValueError, match="unknown table: three"):
        validation.update_document(page, tables)


# The measurement against the real element sets --------------------------------------------

needs_cache = pytest.mark.skipif(
    bool(validation.missing_sets(ROOT, orbit_cache.default_cache_dir())),
    reason="the validation's element sets are not in the cache: run orbit-watch fetch-orbits "
    "for examples/real/reference-orbits.json and validation/real/reference-orbits.json",
)


@needs_cache
def test_the_measurement_gives_the_committed_files(capsys):
    assert main(["measure-method", "--root", str(ROOT), "--check"]) == 0
    assert "0 file(s) out of date" in capsys.readouterr().out


@needs_cache
def test_the_known_answers_make_calibration_tasks():
    inputs = validation.load_inputs(ROOT, orbit_cache.default_cache_dir())
    for entry in KNOWN["entries"]:
        observations = (ROOT / entry["group"] / "observations" / entry["file"]).read_bytes()
        request, delivered, report, verdict = calibration.build_real_files(
            entry, observations, inputs.catalog(entry["norad_id"]), f"test|{entry['file']}"
        )
        assert delivered == observations
        assert verdict == ("pass" if entry["expected"] == "approve" else "fail"), entry["file"]
        assert json.loads(request)["simulated"] is False
        assert "Measurement" not in json.loads(request)["title"]
        assert calibration.REAL_KINDS[calibration.real_kind(entry)] == entry["expected"]
        assert calibration.challenge_text(calibration.real_kind(entry), entry["file"])
        assert json.loads(report)["checks"]


def test_a_real_task_refuses_another_file():
    entry = KNOWN["entries"][0]
    with pytest.raises(ValueError, match="not the file the known answer names"):
        calibration.build_real_files(entry, b"{}", b"{}", "test")

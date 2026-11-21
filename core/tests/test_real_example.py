"""The committed real observations from SCORE (phase 5, step 5.2).

The files are checked offline. The quality reports are regenerated from the real element sets
that ``examples/real/reference-orbits.json`` names, and those tests are skipped without the
local cache (decision P5-05).
"""

import json
import re
from pathlib import Path

import pytest

from orbit_watch import orbit_cache, quality
from orbit_watch.allowlist import DEFAULT_EXCLUDED_NAME_PATTERNS
from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import parse_catalog
from orbit_watch.formats import owjson
from orbit_watch.score import NSF_STATEMENT

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "real"
FILES = sorted((EXAMPLE / "observations").glob("*.json"))
SETS = {path.name: owjson.read_observation_set(path.read_bytes()) for path in FILES}
MANIFEST = orbit_cache.parse_manifest((EXAMPLE / "reference-orbits.json").read_bytes())


def test_there_are_real_tracks_from_several_instruments():
    assert len(FILES) >= 15
    instruments = {s.station.name for s in SETS.values()}
    assert len(instruments) >= 5
    assert len({s.station.id for s in SETS.values()}) >= 5


@pytest.mark.parametrize("name", sorted(SETS))
def test_every_file_names_its_source_observers_and_licence(name):
    document = json.loads((EXAMPLE / "observations" / name).read_text())
    assert document["format_version"] == "1.1" and document["simulated"] is False
    origin = document["source"]["origin"]
    assert origin["licence"] == "CC-BY-4.0" and origin["url"] == "https://score.cps.iau.org"
    assert origin["observers"]
    assert len(origin["observation_ids"]) == len(document["observations"])
    assert document["source"]["converted_from"] == "score"


def test_the_credits_name_every_file_and_observer():
    credits = (EXAMPLE / "CREDITS.md").read_text()
    for name, observation_set in SETS.items():
        assert name in credits
        for orcid in observation_set.source["origin"]["observers"]:
            assert f"https://orcid.org/{orcid}" in credits
    assert NSF_STATEMENT.split(" the NSF NOIRLab")[0] in credits.replace("\n> ", " ")
    assert "SatChecker" in credits


def test_only_civilian_objects():
    patterns = [re.compile(p, re.IGNORECASE) for p in DEFAULT_EXCLUDED_NAME_PATTERNS]
    for observation_set in SETS.values():
        name = observation_set.target.name or ""
        assert not any(p.search(name) for p in patterns), name


def test_no_real_element_set_is_committed():
    for path in EXAMPLE.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert "tle_line" not in text and "MEAN_MOTION" not in text, path


def test_the_windows_and_the_track_left_out():
    tracks = json.loads((EXAMPLE / "tracks.json").read_text())
    objects = {s.target.norad_id for s in SETS.values()}
    assert {w["norad_id"] for w in tracks["windows"]} == objects
    assert all(w["norad_id"] not in objects for w in tracks["left_out"])


def test_the_manifest_names_a_set_for_every_object():
    assert {e.norad_id for e in MANIFEST.entries} == {s.target.norad_id for s in SETS.values()}


needs_cache = pytest.mark.skipif(
    bool(orbit_cache.missing(MANIFEST, orbit_cache.default_cache_dir())),
    reason="the example's element sets are not in the cache: run orbit-watch fetch-orbits "
    "../examples/real/reference-orbits.json",
)


@pytest.fixture(scope="module")
def catalog():
    return parse_catalog(orbit_cache.catalog_from_cache(MANIFEST, orbit_cache.default_cache_dir()))


@needs_cache
def test_every_track_has_a_reference_orbit_within_a_week(catalog):
    for observation_set in SETS.values():
        times = [o.time for o in observation_set.observations]
        middle = min(times) + (max(times) - min(times)) / 2
        nearest = catalog.nearest(observation_set.target.norad_id, middle)
        assert abs((nearest.epoch - middle).total_seconds()) < 7 * 86400


@needs_cache
@pytest.mark.parametrize("station", sorted({s.station.id for s in SETS.values()}))
def test_the_quality_reports_are_up_to_date(catalog, station):
    sets = [SETS[path.name] for path in FILES if SETS[path.name].station.id == station]
    report = quality.score_station(sets, catalog)
    committed = EXAMPLE / "quality" / station
    assert dumps_pretty(report, sort_keys=False) == committed.with_suffix(".json").read_text()
    assert quality.render_text(report) == committed.with_suffix(".txt").read_text()

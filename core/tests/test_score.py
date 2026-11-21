"""Real observations from SCORE (phase 5, step 5.2; decision P5-06).

No test calls SCORE. The stand-in observations are made up for the tests, with ORCID-shaped
iDs that name nobody (0000-0000-0000-000X).
"""

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from orbit_watch.cli import main
from orbit_watch.formats import owjson
from orbit_watch.schema import validate
from orbit_watch.score import (
    FETCH_FORMAT,
    PAGE_SIZE,
    PAUSE_S,
    Assumed,
    ScoreError,
    angle_uncertainty,
    convert,
    credits_markdown,
    distance_m,
    fetch_window,
    file_name,
)

START = datetime(2024, 5, 8, 21, 40, tzinfo=UTC)
LEIDEN = (52.15399, 4.49085, 8.0)


def item(n, seconds=0.0, place=LEIDEN, observers=("0000-0000-0000-0001",), **changes):
    moment = START + timedelta(seconds=seconds)
    base = {
        "id": n,
        "satellite_number": 58296,
        "satellite_name": "A STAND-IN",
        "obs_time_utc": moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "obs_time_uncert_sec": 0.001,
        "sat_ra_deg": 185.0 + n / 1000,
        "sat_dec_deg": 25.0,
        "sigma_2_ra": None,
        "sigma_2_dec": None,
        "obs_lat_deg": place[0],
        "obs_long_deg": place[1],
        "obs_alt_m": place[2],
        "instrument": "a video camera",
        "obs_orc_id": list(observers),
        "apparent_mag": 6.0,
        "potentially_discrepant": False,
    }
    base.update(changes)
    return base


def fetched(*items):
    return {
        "format": FETCH_FORMAT,
        "retrieved": "2026-11-21T08:00:00.000Z",
        "count": len(items),
        "items": list(items),
    }


ASSUMED = Assumed(angle_uncertainty_arcsec=60.0)


# Converting -------------------------------------------------------------------------------


def test_a_track_becomes_an_observation_set_that_names_its_origin():
    sets, skipped = convert([fetched(item(1), item(2, 0.04), item(3, 0.08))], ASSUMED)
    assert skipped == {} and len(sets) == 1
    observation_set = sets[0]
    document = observation_set.to_document()
    assert document["format_version"] == "1.1" and document["simulated"] is False
    assert validate(document, "observation-set") == []
    origin = document["source"]["origin"]
    assert origin["licence"] == "CC-BY-4.0"
    assert origin["observers"] == ["0000-0000-0000-0001"]
    assert origin["observation_ids"] == ["1", "2", "3"]
    assert origin["assumed_angle_uncertainty_arcsec"] == 60.0
    assert "assumed by the converter, not declared by the observer" in document["source"]["notes"]
    station = document["station"]
    assert (station["latitude_deg"], station["longitude_deg"]) == LEIDEN[:2]  # as published
    first = document["observations"][0]
    assert first["frame"] == "ICRF" and first["angle_uncertainty_arcsec"] == 60.0
    # It reads back as it was written.
    text = owjson.write_observation_set(observation_set)
    assert owjson.read_observation_set(text.encode()).source["origin"]["observation_ids"] == [
        "1",
        "2",
        "3",
    ]
    assert file_name(observation_set).startswith("58296-20240508T2140-SCORE-")


def test_an_uncertainty_score_gives_is_used():
    assert angle_uncertainty({"sigma_2_ra": 4.0, "sigma_2_dec": 9.0}) == 3.0
    assert angle_uncertainty({"sigma_2_ra": 0.0, "sigma_2_dec": 9.0}) is None  # 0 means none
    sets, _ = convert([fetched(item(1, sigma_2_ra=4.0, sigma_2_dec=9.0))], ASSUMED)
    document = sets[0].to_document()
    assert document["observations"][0]["angle_uncertainty_arcsec"] == 3.0
    assert "assumed_angle_uncertainty_arcsec" not in document["source"]["origin"]


def test_without_an_assumption_such_observations_are_left_out():
    sets, skipped = convert(
        [fetched(item(1), item(2, obs_time_uncert_sec=0.0, sigma_2_ra=1.0, sigma_2_dec=1.0))]
    )
    assert sets == []
    assert skipped == {
        "no angle uncertainty, and none assumed": 1,
        "no time uncertainty, and none assumed": 1,
    }


def test_brightness_only_and_placeless_observations_are_left_out():
    _, skipped = convert(
        [fetched(item(1, sat_ra_deg=None), item(2, obs_lat_deg=None), item(3))], ASSUMED
    )
    assert skipped == {"no position (brightness only)": 1, "no observer's place": 1}


def test_a_gap_starts_a_new_track_at_the_same_station():
    sets, _ = convert([fetched(item(1), item(2, 2.0), item(3, 3600.0))], ASSUMED)
    assert [len(s.observations) for s in sets] == [2, 1]
    assert sets[0].station.id == sets[1].station.id


def test_a_phone_that_jitters_is_one_station_and_one_that_moves_is_not():
    near = (LEIDEN[0] + 0.0001, LEIDEN[1], LEIDEN[2])  # about 11 m north
    far = (LEIDEN[0] + 0.01, LEIDEN[1], LEIDEN[2])  # about 1.1 km north
    assert 10 < distance_m(LEIDEN, near) < 12
    sets, _ = convert([fetched(item(1), item(2, 1.0, near), item(3, 2.0, far))], ASSUMED)
    assert [len(s.observations) for s in sets] == [2, 1]
    assert sets[0].station.id != sets[1].station.id
    assert "differ by up to 11 m" in sets[0].source["notes"]


def test_files_fetched_apart_share_a_station():
    one = fetched(item(1))
    two = fetched(item(2, 86400.0, (LEIDEN[0] + 0.0001, LEIDEN[1], LEIDEN[2])))
    sets, _ = convert([one, two], ASSUMED)
    assert len(sets) == 2 and sets[0].station == sets[1].station


def test_other_observers_are_another_station():
    sets, _ = convert([fetched(item(1), item(2, 1.0, observers=("0000-0000-0000-0002",)))], ASSUMED)
    assert len({s.station.id for s in sets}) == 2


def test_the_same_observation_twice_counts_once():
    sets, _ = convert([fetched(item(1), item(2, 1.0)), fetched(item(2, 1.0))], ASSUMED)
    assert len(sets[0].observations) == 2


def test_the_credits_name_every_observer_and_the_statements():
    sets, _ = convert([fetched(item(1), item(2, 1.0, observers=("0000-0000-0000-0002",)))], ASSUMED)
    text = credits_markdown(sets)
    assert "https://orcid.org/0000-0000-0000-0001" in text
    assert "https://orcid.org/0000-0000-0000-0002" in text
    assert "do not necessarily reflect the views of the NSF NOIRLab" in text
    assert "SatChecker is" in text


# Format 1.1 -------------------------------------------------------------------------------


def test_format_1_0_has_no_origin_and_1_1_needs_one_id_per_observation():
    sets, _ = convert([fetched(item(1), item(2, 1.0))], ASSUMED)
    document = sets[0].to_document()
    older = dict(document, format_version="1.0")
    assert any("origin" in problem for problem in validate(older, "observation-set"))
    document["source"]["origin"]["observation_ids"].pop()
    _, problems = owjson.parse_document(json.dumps(document).encode())
    assert any("one ID per observation" in problem for problem in problems)


# Fetching ---------------------------------------------------------------------------------


class FakeResponse(io.BytesIO):
    status = 200
    headers = None  # no Content-Encoding

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def pages(total):
    everything = [item(n, n) for n in range(1, total + 1)]

    def page(url):
        offset = int(url.rsplit("offset=", 1)[1])
        body = {"items": everything[offset : offset + PAGE_SIZE], "count": total}
        return FakeResponse(json.dumps(body).encode())

    return page


def test_fetching_pages_politely():
    calls, pauses = [], []
    answer = pages(250)

    def opener(request, timeout):
        calls.append(request.full_url)
        return answer(request.full_url)

    document = fetch_window(
        58296, START, START + timedelta(hours=2), opener=opener, sleep=pauses.append
    )
    assert document["count"] == 250 and len(document["items"]) == 250
    assert len(calls) == 3 and pauses == [PAUSE_S, PAUSE_S]
    assert "satellite_number=58296" in calls[0] and "limit=100" in calls[0]
    assert "start_date=2024-05-08T21%3A40%3A00.000Z" in calls[0]
    assert [url.rsplit("offset=", 1)[1] for url in calls] == ["0", "100", "200"]
    assert document["licence"] == "CC-BY-4.0" and document["format"] == FETCH_FORMAT


def test_fetching_stops_at_the_first_error():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 2:
            raise urllib.error.HTTPError(request.full_url, 503, "", {}, io.BytesIO(b""))
        return pages(250)(request.full_url)

    with pytest.raises(ScoreError, match="at least 15 minutes") as error:
        fetch_window(58296, START, START + timedelta(hours=2), opener=opener, sleep=lambda s: None)
    assert error.value.status == 503 and len(calls) == 2


def test_an_unexpected_answer_stops():
    with pytest.raises(ScoreError, match="not the expected JSON"):
        fetch_window(
            58296,
            START,
            START + timedelta(hours=1),
            opener=lambda request, timeout: FakeResponse(b"<html>"),
        )
    with pytest.raises(ValueError):
        fetch_window(58296, START, START)


def test_the_commands(tmp_path, monkeypatch, capsys):
    from orbit_watch import score

    monkeypatch.setattr(score, "fetch_window", lambda n, s, e: fetched(item(1), item(2, 1.0)))
    raw = tmp_path / "raw.json"
    window = ["--start", "2024-05-08T20:30:00Z", "--end", "2024-05-08T22:30:00Z"]
    assert main(["fetch-score", "--catnr", "58296", *window, "-o", str(raw)]) == 0
    out, credits = tmp_path / "out", tmp_path / "CREDITS.md"
    args = ["--out", str(out), "--credits", str(credits)]
    assert main(["convert-score", str(raw), *args]) == 0
    assert "left out 2: no angle uncertainty, and none assumed" in capsys.readouterr().out
    assert main(["convert-score", str(raw), *args, "--assume-angle-uncertainty", "60"]) == 0
    assert "1 track(s) from 1 station(s)" in capsys.readouterr().out
    assert len(list(out.glob("*.json"))) == 1 and "0000-0000-0000-0001" in credits.read_text()

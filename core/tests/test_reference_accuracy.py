"""How far GP sets are from operators' orbits: the measurement of step 6.1 (P6-02, D-60),
and how operators' orbits age between runs (step 6.2, D-61). Every answer comes from a
local stand-in, and every element set is SIMULATED.
"""

import copy
import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest
from test_reference_orbits import SIM, FakeResponse
from test_supgp import history_answer, item, sup_row, supgp_csv

from orbit_watch import reference_accuracy as ra
from orbit_watch.catalog import parse_catalog
from orbit_watch.cli import main
from orbit_watch.fetch import FetchError
from orbit_watch.supgp import sup_sets
from orbit_watch.validation import update_document

FETCHED = datetime(2026, 11, 2, 0, tzinfo=UTC)
TRUTH_EPOCH = "2026-11-01T12:00:00.000000"


def shifted(**changes) -> dict:
    record = copy.deepcopy(SIM)
    record.update(changes)
    return record


def truth_set():
    catalog = parse_catalog(supgp_csv(sup_row(epoch=TRUTH_EPOCH)))
    return sup_sets(catalog, 339001)[0].element_set


def gp_set(**changes):
    record = shifted(EPOCH=TRUTH_EPOCH, **changes)
    return parse_catalog(json.dumps([record]).encode()).element_sets(339001)[0]


# The comparison ---------------------------------------------------------------------------


def test_the_same_orbit_differs_by_nothing():
    result = ra.compare(gp_set(), truth_set())
    assert result["rms_km"] == 0.0 and result["max_km"] == 0.0
    assert result["age_days"] == 0.125  # the middle of the six hours after the epoch


def test_a_set_ahead_in_its_orbit_differs_in_track():
    result = ra.compare(gp_set(MEAN_ANOMALY=float(SIM["MEAN_ANOMALY"]) + 0.01), truth_set())
    assert result["in_track_rms_km"] > 0.9  # about 1.2 km at 7 km/s
    assert result["cross_track_rms_km"] < 0.05 * result["in_track_rms_km"]
    assert result["radial_rms_km"] < 0.2 * result["in_track_rms_km"]
    assert result["in_track_mean_km"] > 0


def test_a_tilted_plane_differs_across_track():
    result = ra.compare(gp_set(INCLINATION=float(SIM["INCLINATION"]) + 0.01), truth_set())
    assert result["cross_track_rms_km"] > 0.5
    assert result["in_track_rms_km"] < 0.1 * result["cross_track_rms_km"]


# Choosing the truth -----------------------------------------------------------------------


def test_the_latest_operator_set_before_the_run_with_the_best_fit():
    body = supgp_csv(
        sup_row("2026-11-01T00:00:00.000000", "CPF", "0.4"),
        sup_row("2026-11-01T00:00:00.000000", "CPF", "0.2", OBJECT_NAME="SIM [B]"),
        sup_row("2026-10-31T00:00:00.000000", "CPF", "0.1", OBJECT_NAME="SIM [C]"),
        sup_row("2026-11-03T00:00:00.000000", "CPF", "0.05", OBJECT_NAME="SIM [future]"),
        sup_row("2026-11-01T06:00:00.000000", "GPS-A", "0.01", OBJECT_NAME="SIM [almanac]"),
    )
    [truth] = ra.choose_truths({"CPF": parse_catalog(body)}, FETCHED)
    assert truth.sup.rms_km == 0.2 and truth.epoch.isoformat().startswith("2026-11-01T00")
    assert truth.orbit == "LEO" and truth.source == "CPF"


def test_at_most_six_objects_per_source_and_orbit_evenly():
    rows = [sup_row(NORAD_CAT_ID=339100 + i, OBJECT_NAME=f"SIM {i}") for i in range(13)]
    truths = ra.choose_truths({"AST-E": parse_catalog(supgp_csv(*rows))}, FETCHED)
    assert [t.norad_id - 339100 for t in truths] == [0, 2, 5, 7, 10, 12]


def test_the_iss_gives_its_last_segments_that_have_begun():
    rows = [
        sup_row((FETCHED - timedelta(hours=6 * k)).strftime("%Y-%m-%dT%H:%M:%S.000000"), "ISS-E")
        for k in range(-2, 12)
    ]
    truths = ra.choose_truths({"ISS-E": parse_catalog(supgp_csv(*rows))}, FETCHED)
    assert len(truths) == ra.ISS_SEGMENTS
    assert max(t.epoch for t in truths) == FETCHED


# A run ------------------------------------------------------------------------------------


def stand_in_run(tmp_path):
    """A complete run in the cache: one source, one object, two GP sets."""
    path = tmp_path / "reference-accuracy" / "20261102T000000Z"
    path.mkdir(parents=True)
    (path / "supgp-AST-E.csv").write_bytes(supgp_csv(sup_row(epoch=TRUTH_EPOCH)))
    anomaly = float(SIM["MEAN_ANOMALY"])
    (path / "satchecker-339001.json").write_bytes(
        history_answer(
            item("2026-10-30T12:00:00.000000", "2026-10-30 20:00:00 UTC", MEAN_ANOMALY=anomaly),
            item("2026-11-01T06:00:00.000000", "2026-11-01 14:00:00 UTC", "spacetrack"),
            item("2026-10-01T00:00:00.000000", "2026-10-01 08:00:00 UTC"),  # too old
            item("2026-11-01T18:00:00.000000", "2026-11-01 20:00:00 UTC"),  # after the truth
            item(TRUTH_EPOCH, "2026-11-01 16:00:00 UTC"),  # the truth itself, as CelesTrak's
        )
    )
    run = {
        "format": ra.RUN_FORMAT,
        "fetched_at": "2026-11-02T00:00:00Z",
        "sources": ["AST-E"],
        "objects": [339001],
        "complete": True,
    }
    (path / ra.RUN_FILE).write_text(json.dumps(run))
    return path


def test_a_run_is_measured_and_named_by_epochs_and_hashes(tmp_path):
    results = ra.measure(ra.load_run(stand_in_run(tmp_path)))
    assert results["format"] == ra.RESULTS_FORMAT and results["simulated"] is False
    assert [t["norad_id"] for t in results["truths"]] == [339001]
    rows = ra.comparison_rows(results)
    assert [c["gp_epoch"] for c in rows] == [
        "2026-10-30T12:00:00.000000",
        "2026-11-01T06:00:00.000000",
    ]
    ages = [c["age_days"] for c in rows]
    assert ages == [2.125, 0.375]  # to the middle of the six hours after 11-01 12:00
    assert rows[1]["gp_data_source"] == "spacetrack" and rows[1]["norad_id"] == 339001
    assert results["same_as_truth"] == 1 and results["not_propagated"] == 0
    text = json.dumps(results)
    assert "MEAN_MOTION" not in text and "tle_line" not in text  # no element set
    assert ra.measure(ra.load_run(stand_in_run(tmp_path / "again"))) == results  # repeatable
    written = ra.dumps_results(results)
    assert json.loads(written) == results
    assert written.count("\n      [0, ") == 2  # one line per comparison


TABLES = {
    "run",
    "sources",
    "newest_set",
    "by_age",
    "leo_by_source",
    "ageing_run",
    "operator_by_age",
    "operator_against_gp",
}


def test_the_tables_fill_the_document(tmp_path):
    results = ra.measure(ra.load_run(stand_in_run(tmp_path)))
    generated = ra.tables(results)
    assert set(generated) == TABLES
    [row] = generated["leo_by_source"].splitlines()[2:]
    cells = row.strip("| ").split(" | ")
    assert cells[0] == "`AST-E`" and len(cells) == 1 + len(ra.AGE_BINS)
    filled = [i for i, cell in enumerate(cells[1:]) if cell != ra.DASH]
    assert filled == [0, 3]  # the sets 0.375 and 2.125 days old
    assert "| `AST-E` | LEO | 1 |" in generated["newest_set"]
    document = "".join(f"<!-- measured:{n} -->\nold\n<!-- /measured:{n} -->\n" for n in generated)
    assert "old" not in update_document(document, generated)


# How operators' orbits age ----------------------------------------------------------------


def earlier_run(tmp_path, name, fetched_at, *rows):
    """A complete run with SupGP sets only, as an earlier run of the same cache."""
    path = tmp_path / "reference-accuracy" / name
    path.mkdir(parents=True)
    (path / "supgp-AST-E.csv").write_bytes(supgp_csv(*rows))
    run = {
        "format": ra.RUN_FORMAT,
        "fetched_at": fetched_at,
        "sources": ["AST-E"],
        "objects": [],
        "complete": True,
    }
    (path / ra.RUN_FILE).write_text(json.dumps(run))
    return path


def test_an_operators_set_against_a_later_one_and_the_gp_set_of_its_time(tmp_path):
    first = earlier_run(
        tmp_path,
        "20261101T080000Z",
        "2026-11-01T08:00:00Z",
        sup_row("2026-11-01T06:00:00.000000"),
        sup_row("2026-11-01T09:00:00.000000", OBJECT_NAME="SIM [ahead]"),  # ahead, like the ISS
        sup_row("2026-11-01T13:00:00.000000", OBJECT_NAME="SIM [after]"),  # after the truth
    )
    later = stand_in_run(tmp_path)
    results = ra.measure(ra.load_run(later), ra.earlier_runs(later))
    assert [r["directory"] for r in results["runs"]] == ["20261101T080000Z", "20261102T000000Z"]
    [pair] = ra.ageing_rows(results)
    assert pair["earlier_run"] == "20261101T080000Z"
    assert pair["set_epoch"] == "2026-11-01T09:00:00.000000"  # the latest at or before 12:00
    assert pair["age_days"] == 0.25  # to the middle of the six hours after 11-01 12:00
    published = sup_sets(parse_catalog((first / "supgp-AST-E.csv").read_bytes()), 339001)[1]
    assert pair["set_sha256"] == published.element_set.sha256
    assert pair["rms_km"] == ra.compare(published.element_set, truth_set())["rms_km"]
    # SatChecker had collected only the sets of 10-01 and 10-30 by 11-01 08:00
    assert pair["gp_epoch"] == "2026-10-30T12:00:00.000000" and pair["gp_age_days"] == 2.125
    [row] = results["summary"]["operator_against_gp"].values()
    closer = pair["rms_km"] < pair["gp_rms_km"]
    assert (row["pairs"], row["operator_closer"], row["gp_closer"]) == (1, closer, not closer)
    generated = ra.tables(results)
    assert f"| `AST-E` | LEO | 0{ra.DASH}0.5 | 1 | 1 |" in generated["operator_by_age"]
    assert (
        "1 pairs of an operator's set and a later one, 0 sets unchanged"
        in (generated["ageing_run"])
    )
    written = ra.dumps_results(results)
    assert json.loads(written) == results
    assert written.count('\n      ["20261101T080000Z", ') == 1  # one line per pair


def test_a_set_unchanged_between_runs_is_counted_not_compared(tmp_path):
    earlier_run(tmp_path, "20261101T180000Z", "2026-11-01T18:00:00Z", sup_row(epoch=TRUTH_EPOCH))
    later = stand_in_run(tmp_path)
    results = ra.measure(ra.load_run(later), ra.earlier_runs(later))
    assert results["operator_ageing"]["rows"] == []
    assert results["operator_ageing"]["unchanged"] == 1


def test_only_complete_runs_before_count_as_earlier(tmp_path):
    first = earlier_run(tmp_path, "20261101T080000Z", "2026-11-01T08:00:00Z", sup_row())
    broken = first.parent / "20261101T120000Z"
    broken.mkdir()
    (broken / ra.RUN_FILE).write_text(json.dumps({"format": ra.RUN_FORMAT, "complete": False}))
    (first.parent / "20261101T160000Z").mkdir()  # no run.json: fetching stopped
    later = stand_in_run(tmp_path)
    earlier_run(tmp_path, "20261103T000000Z", "2026-11-03T00:00:00Z", sup_row())
    assert [r.path.name for r in ra.earlier_runs(later)] == ["20261101T080000Z"]
    assert ra.earlier_runs(first) == []


def test_an_incomplete_run_is_not_used(tmp_path):
    path = stand_in_run(tmp_path)
    run = json.loads((path / ra.RUN_FILE).read_text())
    (path / ra.RUN_FILE).write_text(json.dumps({**run, "complete": False}))
    with pytest.raises(ValueError, match="not a complete run"):
        ra.load_run(path)


# Fetching a run ---------------------------------------------------------------------------


def opener_for(answers):
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        answer = answers(request.full_url)
        if isinstance(answer, int):
            raise urllib.error.HTTPError(request.full_url, answer, "", {}, None)
        return FakeResponse(answer)

    return opener, calls


def answers_for(url):
    if "sup-gp.php" in url:
        source = url.split("SOURCE=")[1].split("&")[0]
        if source == "AST-E":
            return supgp_csv(sup_row(epoch=TRUTH_EPOCH))
        return supgp_csv(sup_row(epoch=TRUTH_EPOCH, data_source=source, NORAD_CAT_ID=339002))
    return history_answer(item("2026-10-30T12:00:00.000000", "2026-10-30 20:00:00 UTC"))


def test_a_run_is_fetched_politely(tmp_path):
    opener, calls = opener_for(answers_for)
    pauses = []
    path = ra.fetch_run(tmp_path, now=lambda: FETCHED, opener=opener, sleep=pauses.append)
    assert [c.split("SOURCE=")[1][:-11] for c in calls[: len(ra.SOURCES)]] == list(ra.SOURCES)
    assert all("get-omm-data" in c for c in calls[len(ra.SOURCES) :])
    assert len(pauses) == len(calls) - 1 and set(pauses) == {2.0}
    assert ra.load_run(path).fetched_at == FETCHED
    with pytest.raises(ValueError, match="at least two hours"):
        ra.fetch_run(tmp_path, now=lambda: FETCHED + timedelta(hours=1), opener=opener)
    later = ra.fetch_run(
        tmp_path, now=lambda: FETCHED + timedelta(hours=3), opener=opener, sleep=pauses.append
    )
    assert ra.run_dirs(tmp_path) == [path, later]


def test_the_first_answer_that_is_not_200_stops_the_run(tmp_path):
    opener, calls = opener_for(lambda url: 503 if "CPF" in url else answers_for(url))
    with pytest.raises(FetchError, match="HTTP 503"):
        ra.fetch_run(tmp_path, now=lambda: FETCHED, opener=opener, sleep=lambda s: None)
    assert len(calls) == 2  # AST-E, then CPF
    assert ra.run_dirs(tmp_path) == []  # incomplete, so not used


def test_the_command(tmp_path, capsys):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    document = "".join(f"<!-- measured:{n} -->\n<!-- /measured:{n} -->\n" for n in TABLES)
    (root / "docs/reference-orbit-accuracy.md").write_text(document)
    cache = tmp_path / "cache"
    args = ["measure-reference-orbits", "--root", str(root), "--cache", str(cache)]
    assert main(args) == 2
    assert "no complete run" in capsys.readouterr().err
    stand_in_run(cache)
    assert main(args) == 0
    assert "2 comparison(s); 0 pair(s) with 0 earlier run(s)" in capsys.readouterr().out
    assert main([*args, "--check"]) == 0
    earlier_run(
        cache,
        "20261101T080000Z",
        "2026-11-01T08:00:00Z",
        sup_row("2026-11-01T06:00:00.000000"),
    )
    assert main([*args, "--check"]) == 1  # an earlier run changes the results
    assert main(args) == 0
    assert "1 pair(s) with 1 earlier run(s)" in capsys.readouterr().out
    written = json.loads((root / "validation/reference-orbits/results.json").read_text())
    assert written["run"]["directory"] == "20261102T000000Z"

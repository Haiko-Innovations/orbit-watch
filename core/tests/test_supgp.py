"""Operators' orbits from CelesTrak's SupGP, and SatChecker's sets over a period (phase 6,
step 6.1, decisions P6-02 and P6-03). Every answer comes from a local stand-in: no test calls
CelesTrak or SatChecker. The element sets are SIMULATED.
"""

import copy
import gzip
import io
import json
import urllib.error
from datetime import UTC, datetime

import numpy as np
import pytest
from test_reference_orbits import SIM, FakeResponse

from orbit_watch.catalog import parse_catalog
from orbit_watch.cli import main
from orbit_watch.fetch import FetchError
from orbit_watch.satchecker import (
    MAX_PERIOD_DAYS,
    SatCheckerError,
    fetch_history,
    history_url,
    parse_history,
)
from orbit_watch.supgp import (
    build_url,
    fetch_supgp,
    is_operator_orbit,
    sup_sets,
)

START = datetime(2026, 10, 25, tzinfo=UTC)
END = datetime(2026, 11, 2, tzinfo=UTC)


def supgp_csv(*rows: dict) -> bytes:
    fields = [*SIM, "RMS", "DATA_SOURCE"]
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(str(row.get(k, "")) for k in fields))
    return ("\n".join(lines) + "\n").encode()


def sup_row(epoch="2026-11-01T00:00:00.000000", data_source="AST-E", rms="0.152", **extra):
    row = copy.deepcopy(SIM)
    row.update({"EPOCH": epoch, "RMS": rms, "DATA_SOURCE": data_source, **extra})
    return row


# SupGP ------------------------------------------------------------------------------------


def test_the_url():
    assert build_url("CATNR", "53807") == (
        "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=53807&FORMAT=csv"
    )
    assert build_url("SOURCE", "AST-E").endswith("?SOURCE=AST-E&FORMAT=csv")
    with pytest.raises(ValueError):
        build_url("GROUP", "starlink")


@pytest.mark.parametrize(
    ("data_source", "operator"),
    [
        ("AST-E", True),
        ("Starlink-E", True),
        ("ISS-E", True),
        ("GLONASS-RE", True),
        ("Transporter-SV", True),
        ("CPF", True),
        ("GPS-A", False),
        ("ISS-TLE", False),
        ("Orbcomm-TLE", False),
        ("SES-11P", False),
        ("", False),
    ],
)
def test_which_sources_are_an_operators_orbit(data_source, operator):
    assert is_operator_orbit(data_source) is operator


def test_fetch_supgp_asks_for_compressed_csv_and_keeps_rms_and_source(tmp_path):
    body = supgp_csv(
        sup_row(),
        sup_row("2026-11-01T06:00:00.000000", "CPF", "0.252", OBJECT_NAME="SIM [HTS]"),
    )
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(gzip.compress(body), headers={"Content-Encoding": "gzip"})

    message = fetch_supgp("CATNR", "339001", tmp_path / "sup.csv", opener=opener)
    assert "2 element set(s)" in message and "sup-gp.php?CATNR=339001" in message
    assert calls[0].get_header("Accept-encoding") == "gzip" and len(calls) == 1
    sets = sup_sets(parse_catalog((tmp_path / "sup.csv").read_bytes()), 339001)
    assert [(s.data_source, s.rms_km, s.operator_orbit) for s in sets] == [
        ("AST-E", 0.152, True),
        ("CPF", 0.252, True),
    ]


def test_the_extra_columns_do_not_change_the_orbit():
    plain = parse_catalog(json.dumps([SIM]).encode()).satellite(339001)
    sup = parse_catalog(supgp_csv(sup_row(epoch=SIM["EPOCH"]))).satellite(339001)
    t = plain.epoch
    assert np.linalg.norm(plain.at(t).position.km - sup.at(t).position.km) < 1e-9


def test_not_again_within_two_hours(tmp_path):
    output = tmp_path / "sup.csv"
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(supgp_csv(sup_row()))

    fetch_supgp("SOURCE", "AST-E", output, opener=opener, now=lambda: 0.0)
    clock = output.stat().st_mtime
    message = fetch_supgp("SOURCE", "AST-E", output, opener=opener, now=lambda: clock + 3600)
    assert "at least two hours between downloads of SupGP data" in message
    assert len(calls) == 1
    fetch_supgp("SOURCE", "AST-E", output, opener=opener, now=lambda: clock + 7300)
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("status", "advice"), [(404, "do not ask for it again"), (503, "at least 15 minutes")]
)
def test_an_answer_that_is_not_200_stops(tmp_path, status, advice):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, status, "", {}, io.BytesIO(b"No"))

    with pytest.raises(FetchError, match=advice) as caught:
        fetch_supgp("CATNR", "1", tmp_path / "sup.csv", opener=opener)
    assert caught.value.status == status
    assert len(calls) == 1 and not (tmp_path / "sup.csv").exists()


def test_sets_without_a_data_source_are_refused(tmp_path):
    body = supgp_csv(sup_row(data_source=""))
    with pytest.raises(FetchError, match="without a DATA_SOURCE") as caught:
        fetch_supgp(
            "CATNR", "339001", tmp_path / "sup.csv", opener=lambda r, timeout: FakeResponse(body)
        )
    assert caught.value.status == 200 and not (tmp_path / "sup.csv").exists()


def test_an_answer_without_element_sets_is_refused(tmp_path):
    with pytest.raises(FetchError, match="did not return SupGP data") as caught:
        fetch_supgp(
            "CATNR",
            "339001",
            tmp_path / "sup.csv",
            opener=lambda r, timeout: FakeResponse(b"No SupGP data found"),
        )
    assert caught.value.status == 200


# SatChecker over a period -----------------------------------------------------------------


def history_answer(*items: dict, version="1.9.0") -> bytes:
    return json.dumps(
        {
            "count": len(items),
            "data": list(items),
            "source": "IAU CPS SatChecker",
            "version": version,
        }
    ).encode()


def item(epoch, collected, data_source="celestrak", **elements):
    record = copy.deepcopy(SIM)
    record.update({"EPOCH": epoch, **elements})
    return {
        "data_source": data_source,
        "date_collected": collected,
        "epoch": epoch.replace("T", " ")[:19] + " UTC",
        "orbital_elements": record,
        "satellite_id": 339001,
        "satellite_name": SIM["OBJECT_NAME"],
    }


def test_the_period_url():
    assert history_url(339001, START, END) == (
        "https://satchecker.cps.iau.org/tools/get-omm-data/"
        "?id=339001&id_type=catalog&start_date_jd=2461338.50000000&end_date_jd=2461346.50000000"
    )


def test_every_set_once_with_when_it_was_first_collected():
    later = "2026-10-30T12:00:00.000000"
    answer = history_answer(
        item(later, "2026-10-30 20:00:00 UTC", "spacetrack", MEAN_ANOMALY=12.0),
        item("2026-10-28T00:00:00.000000", "2026-10-28 08:00:00 UTC"),
        item(later, "2026-10-30 16:00:00 UTC", "celestrak", MEAN_ANOMALY=12.0),
    )
    sets = parse_history(answer, 339001)
    assert [s.epoch for s in sets] == ["2026-10-28T00:00:00.000000", later]
    source = sets[1].record["source"]
    assert source["date_collected"] == "2026-10-30 16:00:00 UTC"
    assert source["data_source"] == "celestrak" and source["endpoint"] == "get-omm-data"
    assert source["version"] == "1.9.0" and source["original_sha256"] == sets[1].sha256
    wrapper = {"format": "orbit-watch/gp-catalog", "records": [s.record for s in sets]}
    catalog = parse_catalog(json.dumps(wrapper).encode())
    assert len(catalog.sets[339001]) == 2


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        (b"[]", "not the expected JSON"),
        (b'{"data": {}}', "no list of element sets"),
        (json.dumps({"data": [{"orbital_elements": {"EPOCH": "x"}}]}).encode(), "lacks OMM"),
    ],
)
def test_an_unexpected_answer_stops(body, problem):
    with pytest.raises(SatCheckerError, match=problem):
        parse_history(body, 339001)


def test_another_object_is_refused():
    with pytest.raises(SatCheckerError, match="of object 339001, not 25544"):
        parse_history(history_answer(item("2026-10-28T00:00:00.000000", "x")), 25544)


def test_one_request_never_retried_and_a_month_at_most():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 429, "", {}, io.BytesIO(b"slow down"))

    with pytest.raises(SatCheckerError, match="HTTP 429") as caught:
        fetch_history(339001, START, END, opener=opener)
    assert caught.value.status == 429 and len(calls) == 1
    with pytest.raises(ValueError, match=f"at most {MAX_PERIOD_DAYS} days"):
        fetch_history(339001, datetime(2026, 9, 1, tzinfo=UTC), END, opener=opener)
    with pytest.raises(ValueError, match="end after it starts"):
        fetch_history(339001, END, START, opener=opener)
    assert len(calls) == 1
    with pytest.raises(SatCheckerError, match="not the expected JSON") as caught:
        fetch_history(339001, START, END, opener=lambda r, timeout: FakeResponse(b"<html>"))
    assert caught.value.status == 200


# The commands -----------------------------------------------------------------------------


def test_the_commands(tmp_path, monkeypatch, capsys):
    from orbit_watch import satchecker, supgp

    monkeypatch.setattr(
        supgp,
        "download_supgp",
        lambda key, value, opener=None: supgp_csv(sup_row()),
    )
    output = tmp_path / "sup.csv"
    assert main(["fetch-supgp", "--source", "AST-E", "-o", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "1 element set(s)" in printed and "supplemental" in printed
    assert main(["fetch-supgp", "--catnr", "1", "--source", "AST-E", "-o", str(output)]) == 2

    monkeypatch.setattr(
        satchecker,
        "fetch_history",
        lambda norad, start, end, opener=None: parse_history(
            history_answer(item("2026-10-28T00:00:00.000000", "2026-10-28 08:00:00 UTC")), norad
        ),
    )
    period = tmp_path / "period.json"
    args = ["fetch-satchecker", "--catnr", "339001", "-o", str(period)]
    assert main([*args, "--start", "2026-10-25T00:00:00Z", "--end", "2026-11-02T00:00:00Z"]) == 0
    assert "1 element set(s)" in capsys.readouterr().out
    document = json.loads(period.read_text())
    assert document["records"][0]["source"]["date_collected"] == "2026-10-28 08:00:00 UTC"
    assert main([*args, "--start", "2026-10-25T00:00:00Z"]) == 2
    assert main([*args, "--near", "2026-10-25T00:00:00Z", "--start", "2026-10-25T00:00:00Z"]) == 2

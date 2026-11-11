from datetime import UTC, datetime

import pytest

from orbit_watch.ids import format_alpha5, parse_catalog_number
from orbit_watch.timeutil import add_seconds, format_utc, parse_utc


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("25544", 25544),
        ("00005", 5),
        ("A0000", 100000),
        ("A0658", 100658),
        ("H9999", 179999),
        ("J0000", 180000),
        ("P0001", 230001),
        ("Z9999", 339999),
        ("101329", 101329),
    ],
)
def test_catalog_numbers(text, number):
    assert parse_catalog_number(text) == number


@pytest.mark.parametrize("number", [1, 99999, 100000, 100658, 179999, 180000, 339999])
def test_alpha5_roundtrip(number):
    assert parse_catalog_number(format_alpha5(number)) == number


@pytest.mark.parametrize("text", ["", "I0001", "O0001", "a0001", "12a45", "0"])
def test_bad_catalog_numbers(text):
    with pytest.raises(ValueError):
        parse_catalog_number(text)


def test_alpha5_range():
    with pytest.raises(ValueError):
        format_alpha5(340000)


def test_time_roundtrip():
    moment = parse_utc("2026-11-01T17:02:10.5Z")
    assert moment == datetime(2026, 11, 1, 17, 2, 10, 500000, tzinfo=UTC)
    assert format_utc(moment) == "2026-11-01T17:02:10.500Z"
    assert format_utc(add_seconds(moment, 0.000001)) == "2026-11-01T17:02:10.500001Z"


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-01T17:02:10",
        "2026-11-01 17:02:10Z",
        "2026-11-01T17:02:10+00:00",
        "2026-13-01T00:00:00Z",
    ],
)
def test_time_rejects(text):
    with pytest.raises(ValueError):
        parse_utc(text)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        format_utc(datetime(2026, 1, 1))

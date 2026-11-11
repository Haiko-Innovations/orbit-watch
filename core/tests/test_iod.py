"""IOD reader and writer. All lines below are synthetic examples written for these tests."""

import math

import pytest

from orbit_watch.formats import iod
from orbit_watch.model import ObservationSet, Station, Target


def one(line, **kwargs):
    result = iod.read_iod(line, **kwargs)
    assert result.records, result.skipped
    return result.records[0]


@pytest.mark.parametrize(
    ("mx", "value"),
    [
        ("15", 0.001),
        ("56", 0.05),
        ("17", 0.1),
        ("97", 0.9),
        ("18", 1.0),
        ("28", 2.0),
        ("19", 10.0),
        ("99", 90.0),
        ("34", 0.0003),
    ],
)
def test_decode_mx(mx, value):
    assert math.isclose(iod.decode_mx(mx), value)


@pytest.mark.parametrize("value", [0.001, 0.05, 0.1, 0.9, 1.0, 2.0, 10.0, 90.0, 0.0003, 0.07, 3.3])
def test_encode_mx_never_understates(value):
    encoded = iod.encode_mx(value)
    decoded = iod.decode_mx(encoded)
    assert decoded >= value * (1 - 1e-12)
    assert decoded <= value * 10


def test_encode_mx_too_large():
    with pytest.raises(ValueError):
        iod.encode_mx(95)


def test_format_2_radec_j2000():
    record = one("23456 26 901A   9901 G 20261101170210123 16 25 2004938+415259 17 S+075 10")
    obs = record.observation
    assert record.norad_id == 23456
    assert record.station_number == 9901
    assert obs.time.isoformat() == "2026-11-01T17:02:10.123000+00:00"
    assert obs.time_uncertainty_s == pytest.approx(0.01)
    assert obs.angle_type == "radec" and obs.frame == "ICRF"
    assert obs.ra_deg == pytest.approx(15 * (20 + 4.938 / 60))
    assert obs.dec_deg == pytest.approx(41 + 52.59 / 60)
    assert obs.angle_uncertainty_arcsec == pytest.approx(0.1 * 60)
    assert obs.magnitude == pytest.approx(7.5)


def test_format_1_and_negative_declination():
    obs = one("23456 26 901A   9901 E 20261101170210000 18 10 0102035-051530 58").observation
    assert obs.frame == "of-date"
    assert obs.ra_deg == pytest.approx(15 * (1 + 2 / 60 + 3.5 / 3600))
    assert obs.dec_deg == pytest.approx(-(5 + 15 / 60 + 30 / 3600))
    assert obs.angle_uncertainty_arcsec == pytest.approx(5.0)


def test_formats_3_and_7_use_decimal_degrees_for_declination():
    obs3 = one("23456 26 901A   9901 G 20261101170210000 18 35 1200500+123456 15").observation
    obs7 = one("23456 26 901A   9901 G 20261101170210000 18 75 1200305+123456 15").observation
    assert obs3.ra_deg == pytest.approx(15 * (12 + 0.5 / 60))
    assert obs7.ra_deg == pytest.approx(15 * (12 + 30.5 / 3600))
    assert obs3.dec_deg == pytest.approx(12.3456) and obs7.dec_deg == pytest.approx(12.3456)
    assert obs3.angle_uncertainty_arcsec == pytest.approx(0.001 * 3600)


@pytest.mark.parametrize(
    ("line", "az", "el", "unc"),
    [
        (
            "23456 26 901A   9901 G 20261101170210000 18 4  1234530+453015 18",
            123 + 45 / 60 + 30 / 3600,
            45 + 30 / 60 + 15 / 3600,
            1.0,
        ),
        (
            "23456 26 901A   9901 G 20261101170210000 18 5  1234550+453050 18",
            123 + 45.5 / 60,
            45 + 30.5 / 60,
            60.0,
        ),
        (
            "23456 26 901A   9901 G 20261101170210000 18 6  1234567+453456 18",
            123.4567,
            45.3456,
            3600.0,
        ),
    ],
)
def test_azel_formats(line, az, el, unc):
    obs = one(line).observation
    assert obs.angle_type == "azel"
    assert obs.az_deg == pytest.approx(az)
    assert obs.el_deg == pytest.approx(el)
    assert obs.angle_uncertainty_arcsec == pytest.approx(unc)


def test_blank_digits_are_non_significant():
    obs = one("23456 26 901A   9901 F 2026110117021     56 25 2004   +4152   28").observation
    assert obs.time.second == 10 and obs.time.microsecond == 0
    assert obs.ra_deg == pytest.approx(15 * (20 + 4 / 60))
    assert obs.dec_deg == pytest.approx(41 + 52 / 60)


def test_real_world_quirks():
    text = "\n".join(
        [
            # Non-breaking spaces copied from an HTML mail archive.
            "23456 26 901A\u00a0\u00a0 9901 G 20261101170210000 16 25 2004938+415259 17",
            # Short designator field: the station number starts two columns early.
            "23457 26 901B 9901 G 20261101170310000 16 25 2004938+415259 17",
            # Alpha-5 catalogue number and a blank declination sign.
            "A0658 26 902A   9901 G 20261101170410000 16 25 0313440 003352 17",
            # Station status lines carry no observation.
            "\t\t9901 O 20261101",
            "\t\t9901 C 202611011130",
            # Comments and blank lines are ignored.
            "# a comment",
            "",
        ]
    )
    result = iod.read_iod(text)
    assert [r.norad_id for r in result.records] == [23456, 23457, 100658]
    assert result.records[2].observation.dec_deg > 0
    assert len(result.warnings) == 1 and "re-aligned by +2" in result.warnings[0]
    assert len(result.skipped) == 2 and all("status" in s for s in result.skipped)


def test_unsupported_equinox_is_explained():
    result = iod.read_iod("23456 26 901A   9901 G 20261101170210000 16 24 2004938+415259 17")
    assert not result.records
    assert "1950" in result.skipped[0] and "not supported" in result.skipped[0]
    with pytest.raises(iod.IodLineError):
        iod.read_iod(
            "23456 26 901A   9901 G 20261101170210000 16 24 2004938+415259 17", strict=True
        )


def test_missing_uncertainties_need_defaults():
    line = "23456 26 901A   9901 G 20261101170210000    25 2004938+415259"
    assert not iod.read_iod(line).records
    obs = one(
        line, default_angle_uncertainty_arcsec=30.0, default_time_uncertainty_s=0.5
    ).observation
    assert obs.angle_uncertainty_arcsec == 30.0 and obs.time_uncertainty_s == 0.5


@pytest.mark.parametrize(
    "line",
    [
        "23456 26 901A   9901 X 20261101170210000 16 25 2004938+415259 17",  # bad status
        "23456 26 901A   9901 G 20261301170210000 16 25 2004938+415259 17",  # month 13
        "23456 26 901A   9901 G 20261101170210000 16 25 2504938+415259 17",  # RA 25 h
        "23456 26 901A   9901 G 20261101170210000 16 85 2004938+415259 17",  # format 8
        "?????? garbage",
    ],
)
def test_invalid_lines_are_reported(line):
    result = iod.read_iod(line)
    assert not result.records and result.skipped


def test_write_then_read_roundtrip():
    from orbit_watch.model import Observation
    from orbit_watch.timeutil import parse_utc

    station = Station("SIM-X", 60.0, 25.0, 10.0, iod_station_number=9901)
    observations = [
        Observation(
            parse_utc("2026-11-01T17:02:10.250Z"),
            0.01,
            "radec",
            6.0,
            frame="ICRF",
            ra_deg=301.2345678,
            dec_deg=-41.8765432,
        ),
        Observation(
            parse_utc("2026-11-01T17:02:20.000Z"), 0.02, "azel", 30.0, az_deg=359.99, el_deg=12.5
        ),
    ]
    obs_set = ObservationSet(station, Target(339001), observations, simulated=True)
    text = iod.write_iod([obs_set])
    assert text.startswith(iod.SIMULATED_MARKER)
    assert all(len(line) <= 80 for line in text.splitlines())
    result = iod.read_iod(text, strict=True)
    assert result.simulated
    back = [r.observation for r in result.records]
    assert [r.norad_id for r in result.records] == [339001, 339001]
    assert back[0].time == observations[0].time
    assert abs(back[0].ra_deg - 301.2345678) * 3600 < 1.0  # format 2 resolution
    assert abs(back[0].dec_deg + 41.8765432) * 3600 < 0.5
    assert back[0].angle_uncertainty_arcsec >= 6.0
    assert abs(back[1].az_deg - 359.99) * 3600 < 0.5
    assert back[1].angle_uncertainty_arcsec >= 30.0

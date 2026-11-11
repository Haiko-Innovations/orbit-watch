"""CCSDS TDM subset reader and writer. The messages are synthetic test examples."""

from datetime import UTC, datetime

import pytest

from orbit_watch.formats import tdm
from orbit_watch.model import Station

RADEC = """CCSDS_TDM_VERS = 2.0
COMMENT synthetic test message
CREATION_DATE = 2026-11-02T00:00:00
ORIGINATOR = TEST
META_START
COMMENT orbit-watch angle_uncertainty_arcsec=5
COMMENT orbit-watch time_uncertainty_s=0.02
COMMENT orbit-watch simulated=true
TIME_SYSTEM = UTC
PARTICIPANT_1 = SIM-ESPOO
PARTICIPANT_2 = 23456
MODE = SEQUENTIAL
PATH = 2,1
ANGLE_TYPE = RADEC
REFERENCE_FRAME = EME2000
META_STOP
DATA_START
ANGLE_1 = 2026-305T17:02:10.5 -58.765
ANGLE_2 = 2026-305T17:02:10.5 41.5
MAG = 2026-305T17:02:10.5 7.25
ANGLE_1 = 2026-11-01T17:02:20Z 301.5
ANGLE_2 = 2026-11-01T17:02:20Z 42.0
RANGE = 2026-11-01T17:02:20Z 1234.5
DATA_STOP
"""

STATIONS = {"SIM-ESPOO": Station("SIM-ESPOO", 60.205, 24.655, 40.0)}


def test_read_radec():
    result = tdm.read_tdm(RADEC)
    sets = tdm.segments_to_sets(result, STATIONS)
    assert len(sets) == 1
    obs_set = sets[0]
    assert obs_set.simulated and obs_set.target.norad_id == 23456
    first, second = obs_set.observations
    assert first.time == datetime(2026, 11, 1, 17, 2, 10, 500000, tzinfo=UTC)  # day 305
    assert first.ra_deg == pytest.approx(301.235)  # -58.765 normalised
    assert first.frame == "ICRF" and first.magnitude == 7.25
    assert first.angle_uncertainty_arcsec == 5 and first.time_uncertainty_s == 0.02
    assert second.dec_deg == 42.0
    assert any("RANGE ignored" in w for w in result.warnings)


def test_defaults_when_comments_missing():
    text = RADEC.replace("COMMENT orbit-watch angle_uncertainty_arcsec=5\n", "")
    with pytest.raises(tdm.TdmError, match="angle_uncertainty_arcsec"):
        tdm.read_tdm(text)
    result = tdm.read_tdm(text, default_angle_uncertainty_arcsec=9)
    assert result.segments[0].observations[0].angle_uncertainty_arcsec == 9


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("TIME_SYSTEM = UTC", "TIME_SYSTEM = TAI", "TIME_SYSTEM"),
        ("REFERENCE_FRAME = EME2000", "REFERENCE_FRAME = ITRF2000", "REFERENCE_FRAME"),
        ("ANGLE_TYPE = RADEC", "ANGLE_TYPE = XEYN", "ANGLE_TYPE"),
        ("ANGLE_2 = 2026-305T17:02:10.5 41.5\n", "", "share the timetag"),
        ("CCSDS_TDM_VERS = 2.0", "CCSDS_TDM_VERS = 0.12", "CCSDS_TDM_VERS"),
        ("ORIGINATOR = TEST\n", "", "ORIGINATOR"),
        ("DATA_STOP\n", "", "ends inside"),
        ("PATH = 2,1", "CORRECTION_ANGLE_1 = 0.1", "CORRECTION_ANGLE_1"),
        (
            "ANGLE_2 = 2026-11-01T17:02:20Z 42.0",
            "ANGLE_2 = 2026-11-01T17:02:20Z 142.0",
            "out of range",
        ),
        ("ANGLE_TYPE = RADEC", "angle_type = RADEC", "uppercase"),
    ],
)
def test_rejects_unsupported_or_invalid(old, new, message):
    with pytest.raises(tdm.TdmError, match=message):
        tdm.read_tdm(RADEC.replace(old, new))


def test_non_numeric_participant():
    result = tdm.read_tdm(RADEC.replace("PARTICIPANT_2 = 23456", "PARTICIPANT_2 = SAT"))
    with pytest.raises(tdm.TdmError, match="PARTICIPANT_2"):
        tdm.segments_to_sets(result, STATIONS)


def test_write_then_read_roundtrip():
    sets = tdm.segments_to_sets(tdm.read_tdm(RADEC), STATIONS)
    text = tdm.write_tdm(sets, creation_date=datetime(2026, 11, 2, tzinfo=UTC))
    assert "COMMENT SIMULATED DATA" in text
    again = tdm.segments_to_sets(tdm.read_tdm(text), STATIONS)
    assert [o.to_document() for o in again[0].observations] == [
        o.to_document() for o in sets[0].observations
    ]
    assert again[0].simulated

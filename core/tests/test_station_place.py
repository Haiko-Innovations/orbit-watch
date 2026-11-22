"""The station profile is the station's place for every format (phase 5, step 5.6; decisions
P5-11, D-55). Everything here is SIMULATED: SIM-ESPOO's profile and the format examples."""

import json
from pathlib import Path

import pytest
from helpers import packaged

from orbit_watch.formats import load_observation_sets
from orbit_watch.formats.sites import Sites
from orbit_watch.station_place import PlaceError, sites_for

FORMATS = Path(__file__).resolve().parents[2] / "examples/formats"


def profile(**place):
    document = json.loads(packaged("stations/sim-cmos-gps.json"))  # 60.205, 24.655, 40 m
    document["station"].update(place)
    return document


def test_a_json_delivery_names_its_profiles_place():
    data = (FORMATS / "observation-set.json").read_bytes()
    assert sites_for(profile(), data, "json") is None
    assert sites_for(profile(), data, None) is None  # the format is detected


@pytest.mark.parametrize(
    "place",
    [{"latitude_deg": 60.2}, {"longitude_deg": 24.66}, {"altitude_m": 41.0}],
)
def test_a_json_delivery_from_another_place_is_refused(place):
    data = (FORMATS / "observation-set.json").read_bytes()
    with pytest.raises(PlaceError, match="The profile is your station's place") as refused:
        sites_for(profile(**place), data, "json")
    assert refused.value.code == "wrong_place"


def test_an_iod_delivery_is_placed_at_its_profile():
    data = (FORMATS / "observation-set.iod").read_bytes()
    sites = sites_for(profile(latitude_deg=60.2, longitude_deg=24.66), data, "iod")
    (site,) = json.loads(sites)["sites"]
    assert site == {
        "id": "SIM-ESPOO",
        "iod_station_number": 9901,
        "latitude_deg": 60.2,
        "longitude_deg": 24.66,
        "altitude_m": 40.0,
    }
    assert "name" not in site  # the station's name is not published with it
    (observed,) = load_observation_sets("x", data=data, sites=Sites.parse(sites)).sets
    assert (observed.station.latitude_deg, observed.station.longitude_deg) == (60.2, 24.66)
    # A profile without an IOD number places whatever number the file names.
    without = profile()
    del without["station"]["iod_station_number"]
    assert json.loads(sites_for(without, data, "iod"))["sites"][0]["iod_station_number"] == 9901


def test_an_iod_delivery_of_another_station_is_refused():
    data = (FORMATS / "observation-set.iod").read_bytes()
    with pytest.raises(PlaceError, match="names IOD station 9901, and your station's profile 9902"):
        sites_for(profile(iod_station_number=9902), data, "iod")
    two = data + data.replace(b" 9901 ", b" 9902 ")
    with pytest.raises(PlaceError, match="names IOD stations 9901, 9902"):
        sites_for(profile(), two, "iod")


def test_a_tdm_delivery_is_placed_at_its_profile():
    data = (FORMATS / "observation-set.tdm").read_bytes()
    sites = sites_for(profile(altitude_m=12.5), data, "tdm")
    (site,) = json.loads(sites)["sites"]
    assert site == {
        "id": "SIM-ESPOO",
        "latitude_deg": 60.205,
        "longitude_deg": 24.655,
        "altitude_m": 12.5,
    }
    (observed,) = load_observation_sets("x", data=data, sites=Sites.parse(sites)).sets
    assert observed.station.altitude_m == 12.5


def test_a_file_that_cannot_be_read_is_left_to_verification():
    for data, fmt in [(b"not json", "json"), (b"[1, 2]", "json"), (b"\xff\xfe", None)]:
        assert sites_for(profile(), data, fmt) is None

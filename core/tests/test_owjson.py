import copy
import json

import pytest

from orbit_watch.formats import owjson
from orbit_watch.schema import load_schema


@pytest.fixture
def example(examples_dir):
    return json.loads((examples_dir / "formats" / "observation-set.json").read_text())


def test_example_is_valid_and_roundtrips(example, examples_dir):
    data = (examples_dir / "formats" / "observation-set.json").read_bytes()
    obs_set = owjson.read_observation_set(data)
    assert obs_set.simulated is True
    assert owjson.write_observation_set(obs_set) == data.decode()


def test_schema_has_stable_identity():
    schema = load_schema("observation-set")
    assert schema["$id"].endswith("observation-set-1.0.schema.json")
    assert "simulated" in schema["required"]


def problems_for(document):
    _, problems = owjson.parse_document(json.dumps(document).encode())
    return problems


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d.pop("simulated"), "'simulated' is a required property"),
        (lambda d: d["observations"][0].pop("time"), "'time' is a required property"),
        (lambda d: d["observations"][0].update(ra_deg=360.0), "/observations/0/ra_deg"),
        (lambda d: d["observations"][0].update(time="2026-11-01 17:02:10"), "/observations/0/time"),
        (lambda d: d["observations"][0].update(az_deg=10.0), "/observations/0"),
        (lambda d: d["observations"][2].update(frame="ICRF"), "/observations/2"),
        (lambda d: d["observations"][0].update(angle_uncertainty_arcsec=0), "/observations/0"),
        (lambda d: d["target"].update(norad_id="25544"), "/target/norad_id"),
        (lambda d: d.update(extra=True), "Additional properties"),
        (
            lambda d: d["observations"][0].update(time="2026-02-30T00:00:00Z"),
            "not a valid calendar date",
        ),
    ],
)
def test_invalid_documents_have_clear_problems(example, mutate, expected):
    document = copy.deepcopy(example)
    mutate(document)
    problems = problems_for(document)
    assert problems, "expected the document to be rejected"
    assert any(expected in p for p in problems), problems


def test_not_json_and_not_utf8():
    assert "not valid JSON" in owjson.parse_document(b"{")[1][0]
    assert "not UTF-8" in owjson.parse_document(b"\xff\xfe")[1][0]


def test_write_refuses_invalid(example):
    obs_set = owjson.read_observation_set(json.dumps(example).encode())
    obs_set.observations[0] = obs_set.observations[0].__class__(
        **{**obs_set.observations[0].__dict__, "angle_uncertainty_arcsec": -1.0}
    )
    with pytest.raises(owjson.FormatError):
        owjson.write_observation_set(obs_set)

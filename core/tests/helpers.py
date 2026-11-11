"""Shared helpers for tests that need the simulated catalogue and request."""

from __future__ import annotations

import copy
import json
from importlib import resources

from orbit_watch.canonical import dumps_pretty
from orbit_watch.catalog import parse_catalog
from orbit_watch.sim.scenarios import REQUEST


def packaged(name: str) -> bytes:
    return resources.files("orbit_watch.data").joinpath(name).read_bytes()


def catalog_bytes() -> bytes:
    return packaged("catalog.json")


def policy_bytes() -> bytes:
    return packaged("target-policy.json")


def catalog():
    return parse_catalog(catalog_bytes())


def request_bytes(**changes) -> bytes:
    document = copy.deepcopy(REQUEST)
    for key, value in changes.items():
        if key in ("start", "end"):
            document["window"][key] = value
        elif key == "norad_id":
            document["target"] = {"norad_id": value}
        else:
            document[key] = value
    return dumps_pretty(document, sort_keys=False).encode()


def load_json(data: bytes) -> dict:
    return json.loads(data)

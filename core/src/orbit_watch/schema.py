"""JSON Schema loading and validation for Orbit Watch documents."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_FILES = {
    "observation-set": "observation-set-1.0.schema.json",
    "sites": "sites-1.0.schema.json",
    "request": "request-1.0.schema.json",
    "delivery": "delivery-1.0.schema.json",
    "target-policy": "target-policy-1.0.schema.json",
    "station-profile": "station-profile-1.0.schema.json",
}


@cache
def load_schema(kind: str) -> dict[str, Any]:
    try:
        name = SCHEMA_FILES[kind]
    except KeyError:
        raise ValueError(f"unknown schema kind: {kind}") from None
    text = resources.files("orbit_watch.schemas").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


@cache
def _validator(kind: str) -> Draft202012Validator:
    schema = load_schema(kind)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _path(error: Any) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/" + "/".join(parts) if parts else "/"


def validate(document: Any, kind: str) -> list[str]:
    """Return schema violations as sorted "path: message" strings (empty when valid)."""
    errors = _validator(kind).iter_errors(document)
    return sorted(f"{_path(e)}: {e.message}" for e in errors)

"""JSON Schema loading and validation for Orbit Watch documents."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

# Kinds with more than one format version: the document's format_version picks the schema.
VERSIONED_SCHEMA_FILES = {
    "observation-set": {
        "1.0": "observation-set-1.0.schema.json",
        "1.1": "observation-set-1.1.schema.json",
    },
    "request": {
        "1.0": "request-1.0.schema.json",
        "1.1": "request-1.1.schema.json",
    },
}

SCHEMA_FILES = {
    "observation-set": "observation-set-1.0.schema.json",
    "sites": "sites-1.0.schema.json",
    "request": "request-1.0.schema.json",
    "delivery": "delivery-1.0.schema.json",
    "target-policy": "target-policy-1.0.schema.json",
    "station-profile": "station-profile-1.0.schema.json",
    "reviewer-registry": "reviewer-registry-1.0.schema.json",
}


@cache
def load_schema(kind: str, version: str | None = None) -> dict[str, Any]:
    """The schema of a kind; for a versioned kind, of ``version`` (by default the first)."""
    try:
        name = SCHEMA_FILES[kind]
        if version is not None:
            name = VERSIONED_SCHEMA_FILES[kind][version]
    except KeyError:
        raise ValueError(f"unknown schema kind or version: {kind} {version or ''}") from None
    text = resources.files("orbit_watch.schemas").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


@cache
def _validator(kind: str, version: str | None = None) -> Draft202012Validator:
    schema = load_schema(kind, version)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _path(error: Any) -> str:
    parts = [str(p) for p in error.absolute_path]
    return "/" + "/".join(parts) if parts else "/"


def validate(document: Any, kind: str) -> list[str]:
    """Return schema violations as sorted "path: message" strings (empty when valid)."""
    version = None
    versions = VERSIONED_SCHEMA_FILES.get(kind, {})
    if isinstance(document, dict) and document.get("format_version") in versions:
        version = document["format_version"]
    errors = _validator(kind, version).iter_errors(document)
    return sorted(f"{_path(e)}: {e.message}" for e in errors)

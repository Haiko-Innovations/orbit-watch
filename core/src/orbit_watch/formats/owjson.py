"""Reading and writing the Orbit Watch JSON observation format."""

from __future__ import annotations

import json
from typing import Any

from orbit_watch.canonical import dumps_pretty
from orbit_watch.model import ObservationSet
from orbit_watch.schema import validate
from orbit_watch.timeutil import parse_utc


class FormatError(ValueError):
    """The input is not a valid document of the expected format."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


def semantic_problems(document: dict[str, Any]) -> list[str]:
    """Checks that JSON Schema cannot express (run only on schema-valid documents)."""
    problems: list[str] = []
    for index, obs in enumerate(document.get("observations", [])):
        try:
            parse_utc(obs["time"])
        except ValueError as exc:
            problems.append(f"/observations/{index}/time: {exc}")
    return problems


def parse_document(data: bytes) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse and validate JSON bytes. Returns (document or None, problems)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [f"/: not UTF-8 text ({exc.reason} at byte {exc.start})"]
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"/: not valid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})"]
    problems = validate(document, "observation-set")
    if not problems:
        problems = semantic_problems(document)
    return document, problems


def read_observation_set(data: bytes) -> ObservationSet:
    document, problems = parse_document(data)
    if problems or document is None:
        raise FormatError("invalid Orbit Watch observation set", problems)
    return ObservationSet.from_document(document)


def write_observation_set(observation_set: ObservationSet) -> str:
    document = observation_set.to_document()
    problems = validate(document, "observation-set")
    if problems:
        raise FormatError("refusing to write an invalid observation set", problems)
    return dumps_pretty(document, sort_keys=False)

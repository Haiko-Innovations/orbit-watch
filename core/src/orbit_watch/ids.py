"""Satellite catalogue numbers, including the Alpha-5 scheme.

Five-character catalogue fields (TLE, IOD) ran out of digits in 2026. The
Alpha-5 scheme replaces the first digit with a letter: A=10, B=11, ... Z=33,
skipping I and O, so "A0658" means 100658 and "Z9999" means 339999.
"""

from __future__ import annotations

import re

_ALPHA5_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I, no O
_ALPHA5_RE = re.compile(r"^[A-HJ-NP-Z][0-9]{4}$")

MAX_NORAD_ID = 999_999_999
MAX_ALPHA5_ID = 339_999


def parse_catalog_number(text: str) -> int:
    """Parse a catalogue number written as digits or in Alpha-5 form."""
    value = text.strip()
    if not value:
        raise ValueError("empty catalogue number")
    if value.isdigit():
        number = int(value)
    elif _ALPHA5_RE.match(value):
        number = (_ALPHA5_LETTERS.index(value[0]) + 10) * 10_000 + int(value[1:])
    else:
        raise ValueError(f"not a catalogue number: {text!r}")
    if not 1 <= number <= MAX_NORAD_ID:
        raise ValueError(f"catalogue number out of range: {number}")
    return number


def format_alpha5(number: int) -> str:
    """Format a catalogue number in a five-character field (digits or Alpha-5)."""
    if not 1 <= number <= MAX_ALPHA5_ID:
        raise ValueError(f"catalogue number {number} does not fit a five-character field")
    if number < 100_000:
        return f"{number:05d}"
    letter = _ALPHA5_LETTERS[number // 10_000 - 10]
    return f"{letter}{number % 10_000:04d}"

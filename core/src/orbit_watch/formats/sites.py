"""Station sites files: coordinates for formats that carry only a station identifier."""

from __future__ import annotations

import json
from pathlib import Path

from orbit_watch.formats.owjson import FormatError
from orbit_watch.model import Station
from orbit_watch.schema import validate


class Sites:
    """Lookup of stations by identifier or IOD station number."""

    def __init__(self, stations: list[Station], simulated: bool = False):
        self.stations = stations
        self.simulated = simulated
        self._by_id = {s.id: s for s in stations}
        self._by_iod = {
            s.iod_station_number: s for s in stations if s.iod_station_number is not None
        }

    @classmethod
    def empty(cls) -> Sites:
        return cls([])

    @classmethod
    def load(cls, path: str | Path) -> Sites:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        problems = validate(document, "sites")
        if problems:
            raise FormatError(f"invalid sites file {path}", problems)
        stations = [
            Station.from_document({k: v for k, v in s.items() if k != "simulated"})
            for s in document["sites"]
        ]
        return cls(stations, simulated=bool(document.get("simulated", False)))

    def by_id(self, station_id: str) -> Station | None:
        return self._by_id.get(station_id)

    def by_iod_number(self, number: int) -> Station | None:
        station = self._by_iod.get(number)
        if station is None:
            station = self._by_id.get(f"{number:04d}") or self._by_id.get(str(number))
        return station

"""The network map: how punctual each recorded station is, now and this week.

Data comes from Data Explorer (KQL NetworkStatus in kql/08_network.kql), one
query for all stations, cached for 10 minutes. Coordinates come from the
station list the search uses, looked up once by name.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from .stations import HubMatcher, StationIndex

log = logging.getLogger(__name__)
Rows = list[dict[str, Any]]
MIN_DEPARTURES = 5  # fewer departures in a window: no share shown for it


def _window(departures: int, on_time: int, cancelled: int) -> dict[str, Any]:
    return {
        "departures": departures,
        "onTime": round(on_time / departures, 3) if departures >= MIN_DEPARTURES else None,
        "cancelled": cancelled,
    }


class NetworkStatus:
    def __init__(
        self,
        run: Callable[[str], Rows],
        hubs: HubMatcher,
        stations: StationIndex,
        ttl: float = 600.0,
    ) -> None:
        self.run, self.hubs, self.stations, self.ttl = run, hubs, stations, ttl
        self._cached: tuple[float, list[dict[str, Any]]] | None = None
        self._coords: dict[int, tuple[float, float] | None] = {}
        self._lock = threading.Lock()

    def coordinates(self, eva: int, name: str) -> tuple[float, float] | None:
        if eva not in self._coords:
            hits = [
                s for s in self.stations.search(name, limit=3)
                if 47.2 <= s.lat <= 55.1 and 5.8 <= s.lon <= 15.1  # inside Germany
            ]  # fmt: skip
            self._coords[eva] = (hits[0].lat, hits[0].lon) if hits else None
            if not hits:
                log.warning("no coordinates for hub %s (%s)", eva, name)
        return self._coords[eva]

    def build(self, rows: Rows) -> list[dict[str, Any]]:
        by_eva = {int(r["eva"]): r for r in rows}
        out = []
        for group_eva, (main, evas) in sorted(
            self.hubs.groups().items(), key=lambda g: g[1][0].name
        ):
            coords = self.coordinates(group_eva, main.name)
            if coords is None:
                continue
            sums = dict.fromkeys(
                ("week_departures", "week_on_time", "week_cancelled",
                 "now_departures", "now_on_time", "now_cancelled"), 0,
            )  # fmt: skip
            for eva in evas:
                r = by_eva.get(eva)
                if r:
                    for k in sums:
                        sums[k] += int(r.get(k) or 0)
            out.append({
                "eva": group_eva,
                "name": main.name,
                "lat": round(coords[0], 4),
                "lon": round(coords[1], 4),
                "national": main.priority == 1,
                "now": _window(sums["now_departures"], sums["now_on_time"], sums["now_cancelled"]),
                "week": _window(sums["week_departures"], sums["week_on_time"], sums["week_cancelled"]),
            })  # fmt: skip
        return out

    def stations_status(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            hit = self._cached
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        value = self.build(self.run("NetworkStatus()"))
        with self._lock:
            self._cached = (now, value)
        return value

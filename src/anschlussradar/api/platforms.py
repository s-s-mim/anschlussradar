"""Platform numbers from our own DB data, where Transitous has none.

Transitous leaves the platform empty for some stops, often underground S-Bahn
stations such as Frankfurt Hbf (tief). At the recorded hubs we have DB's planned
platform of every train and any announced change. A leg without a platform gets
ours when the train number and the planned time (within 2 minutes) match.
Only upcoming trains are covered: the collector loads DB's plans a few hours ahead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from .refresh import Refresh

MATCH_WINDOW = timedelta(minutes=2)


@dataclass(frozen=True)
class Platform:
    current: str
    planned: str


class PlatformProvider(Protocol):
    def find(self, eva: int, number: str, when: datetime, side: str) -> Platform | None: ...


class NoPlatforms:
    def find(self, eva: int, number: str, when: datetime, side: str) -> Platform | None:
        return None


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class KustoPlatforms:
    def __init__(self, query: Callable[[], list[dict[str, Any]]], refresh_s: float = 300.0) -> None:
        self.query = query
        # (eva, train number) -> rows of (side, planned time, platform)
        self._rows: dict[tuple[int, str], list[tuple[str, datetime, Platform]]] = {}
        self._refresher = Refresh(self._load, refresh_s, "platforms")

    def load_rows(self, rows: list[dict[str, Any]]) -> None:
        data: dict[tuple[int, str], list[tuple[str, datetime, Platform]]] = {}
        for r in rows:
            key = (int(r["eva"]), str(r["number"]))
            for side in ("dep", "arr"):
                when, current = _time(r.get(f"{side}_pt")), r.get(f"{side}_platform")
                if when is None or not current:
                    continue
                planned = r.get(f"{side}_planned_platform") or current
                data.setdefault(key, []).append((side, when, Platform(str(current), str(planned))))
        self._rows = data

    def _load(self) -> None:
        self.load_rows(self.query())

    def warm(self) -> None:
        self._refresher.warm()

    def find(self, eva: int, number: str, when: datetime, side: str) -> Platform | None:
        self._refresher.ensure()
        for s, t, platform in self._rows.get((eva, number), []):
            if s == side and abs(t - when) <= MATCH_WINDOW:
                return platform
        return None

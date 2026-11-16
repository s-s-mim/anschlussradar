"""The station page: next departures and punctuality by hour at a recorded hub.

Data comes from Data Explorer (KQL StationBoard and StationHourly in
kql/06_station.kql), cached per station: departures for 60 seconds, the hourly
punctuality for an hour. Only recorded hubs have a page, because only they are
polled.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .messages import current

log = logging.getLogger(__name__)
BERLIN = ZoneInfo("Europe/Berlin")
Rows = list[dict[str, Any]]


def _dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(BERLIN).isoformat() if t else None


def departure(row: dict[str, Any]) -> dict[str, Any]:
    planned, changed = _dt(row.get("dep_pt")), _dt(row.get("dep_ct"))
    delay = round((changed - planned).total_seconds() / 60) if planned and changed else None
    return {
        "category": row.get("category"),
        "number": row.get("number"),
        "line": row.get("line") or None,
        "destination": row.get("destination"),
        "departurePlanned": _iso(planned),
        "departure": _iso(changed or planned),
        "delay": delay,
        "platform": row.get("dep_cp") or row.get("dep_pp"),
        "platformPlanned": row.get("dep_pp"),
        "cancelled": bool(row.get("cancelled")),
        "messages": [m.to_dict() for m in current(row.get("messages"))],
    }


def hourly(rows: Rows) -> list[dict[str, Any]]:
    by_hour = {int(r["hour"]): r for r in rows}
    out = []
    for h in range(24):
        r = by_hour.get(h)
        n = int(r["departures"]) if r else 0
        out.append({
            "hour": h,
            "departures": n,
            "onTime": round(int(r["on_time"]) / n, 3) if r and n else None,
            "cancelled": int(r["cancelled"]) if r else 0,
        })  # fmt: skip
    return out


def _dyn(evas: list[int]) -> str:
    return "dynamic([" + ",".join(str(int(e)) for e in evas) + "])"


def _kdt(t: datetime) -> str:
    return f"datetime({t.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ})"


class StationBoards:
    def __init__(
        self,
        run: Callable[[str], Rows],
        board_ttl: float = 60.0,
        hourly_ttl: float = 3600.0,
        window_minutes: int = 90,
    ) -> None:
        self.run = run
        self.board_ttl, self.hourly_ttl, self.window = board_ttl, hourly_ttl, window_minutes
        self._cache: dict[tuple[str, int], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: tuple[str, int], ttl: float, load: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = load()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def board(self, group_eva: int, evas: list[int], now: datetime) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            start = now - timedelta(minutes=5)
            end = now + timedelta(minutes=self.window)
            rows = self.run(f"StationBoard({_dyn(evas)}, {_kdt(start)}, {_kdt(end)})")
            return [departure(r) for r in rows]

        result: list[dict[str, Any]] = self._cached(("board", group_eva), self.board_ttl, load)
        return result

    def hourly(self, group_eva: int, evas: list[int]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._cached(
            ("hourly", group_eva),
            self.hourly_ttl,
            lambda: hourly(self.run(f"StationHourly({_dyn(evas)})")),
        )
        return result

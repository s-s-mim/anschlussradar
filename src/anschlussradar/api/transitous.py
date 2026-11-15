"""Client for the Transitous journey planner (MOTIS 2 API).

Usage policy (transitous.org/api): free and open-source, non-commercial projects
only; every request carries a User-Agent with app name, version and a contact;
many /plan requests (more than about 720 a day) need coordination with the team.
That is why plans are cached and requests are counted per day.

Endpoint: GET {base}/api/v5/plan
  fromPlace, toPlace   'lat,lon' or a stop id
  time                 ISO 8601; departure time, or arrival time with arriveBy=true
  arriveBy, transitModes, numItineraries, detailedTransfers
"""

from __future__ import annotations

import threading
import time as _time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx

# Rail modes only: the reliability model covers trains, not buses or trams.
RAIL_MODES = (
    "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_FAST_RAIL,REGIONAL_RAIL,SUBURBAN,RAIL"
)


class TransitousError(Exception):
    pass


@dataclass
class UsageCounter:
    """Counts /plan requests per UTC day, shown in /health."""

    day: date = field(default_factory=lambda: datetime.now(UTC).date())
    plan_requests: int = 0
    cache_hits: int = 0

    def add(self, cached: bool) -> None:
        today = datetime.now(UTC).date()
        if today != self.day:
            self.day, self.plan_requests, self.cache_hits = today, 0, 0
        if cached:
            self.cache_hits += 1
        else:
            self.plan_requests += 1


class TtlCache:
    def __init__(self, ttl_s: float, max_entries: int = 500) -> None:
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < _time.monotonic():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return item[1]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (_time.monotonic() + self.ttl_s, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)


class TransitousClient:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        cache_seconds: int = 120,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._cache = TtlCache(cache_seconds)
        self.usage = UsageCounter()

    def plan(
        self,
        from_place: str,
        to_place: str,
        when: datetime,
        arrive_by: bool = False,
        rail_only: bool = True,
        num_itineraries: int = 5,
    ) -> dict[str, Any]:
        # Round to 5 minutes for the cache: searches a minute apart share one request.
        rounded = when.astimezone(UTC).replace(second=0, microsecond=0)
        rounded = rounded.replace(minute=rounded.minute - rounded.minute % 5)
        params = {
            "fromPlace": from_place,
            "toPlace": to_place,
            "time": rounded.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "arriveBy": "true" if arrive_by else "false",
            "detailedTransfers": "false",
            "numItineraries": str(num_itineraries),
        }
        if rail_only:
            params["transitModes"] = RAIL_MODES
        key = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache.get(key)
        if cached is not None:
            self.usage.add(cached=True)
            return cached  # type: ignore[no-any-return]

        try:
            resp = self._http.get(
                f"{self.base_url}/api/v5/plan", params=params, headers=self._headers
            )
        except httpx.TransportError as exc:
            raise TransitousError(f"journey planner not reachable: {type(exc).__name__}") from exc
        self.usage.add(cached=False)
        if resp.status_code != 200:
            raise TransitousError(f"journey planner answered HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        self._cache.put(key, data)
        return data

"""Hourly weather at every recorded hub, from Bright Sky (open data of the DWD).

Snow, storms and heat change how often transfers work, so the model gets the
weather as a feature once a few weeks of it are collected. One call per station
group per hour (about 70 calls), stored like the timetable data: the raw JSON in
Blob Storage, one row per hub and hour in the Data Explorer table WeatherHourly.

Bright Sky: https://brightsky.dev, data: Deutscher Wetterdienst (DWD), free to use
with attribution.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..api.stations import normalize
from ..storage.base import Sink
from .hubs import Hub

log = logging.getLogger(__name__)

FIELDS = (
    "temperature",
    "precipitation",
    "wind_speed",
    "wind_gust_speed",
    "visibility",
    "cloud_cover",
    "condition",
)


@dataclass(frozen=True, slots=True)
class Place:
    group_eva: int
    name: str
    lat: float
    lon: float


def hub_places(hubs: list[Hub], stations: dict[str, Any]) -> list[Place]:
    """One place per station group, located by name in the public station list.

    Hubs whose name is not found are skipped and logged; levels of one station
    share its weather, so only the main EVA of each group is used.
    """
    by_name = {normalize(s["name"]): s for s in stations.get("stations", [])}
    places, missing = [], []
    for h in hubs:
        if h.eva != h.group_eva:
            continue
        s = by_name.get(normalize(h.name))
        if s is None:
            missing.append(h.name)
            continue
        places.append(Place(h.group_eva, h.name, float(s["lat"]), float(s["lon"])))
    if missing:
        log.warning("no coordinates for %s", ", ".join(missing))
    return places


def weather_blob_path(eva: int, fetched_at: datetime) -> str:
    """Bronze path, next to (not inside) the db/ folder that replay reads."""
    t = fetched_at
    return f"weather/{eva}/{t:%Y}/{t:%m}/{t:%d}/{t:%H}/{t:%Y%m%dT%H%M%S}Z-{uuid.uuid4().hex[:8]}.json.gz"


def to_record(
    place: Place, hour: datetime, data: dict[str, Any], fetched_at: datetime
) -> dict[str, Any] | None:
    """The row for exactly this hour, or None when Bright Sky has no value yet."""
    for w in data.get("weather", []):
        try:
            ts = datetime.fromisoformat(w["timestamp"]).astimezone(UTC)
        except (KeyError, ValueError):
            continue
        if ts == hour:
            row = {k: w.get(k) for k in FIELDS}
            return {
                "eva": place.group_eva,
                "observed_hour": hour.isoformat(),
                **row,
                "source_id": w.get("source_id"),
                "fetched_at": fetched_at.isoformat(),
            }
    return None


def collect(
    places: list[Place],
    sink: Sink,
    http: httpx.Client,
    base_url: str,
    now: datetime,
) -> int:
    """Fetch the last full hour for every place. Returns the number of rows written."""
    hour = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    rows = []
    for p in places:
        params = {
            "lat": f"{p.lat:.4f}",
            "lon": f"{p.lon:.4f}",
            "date": hour.isoformat(),
            "last_date": (hour + timedelta(hours=1)).isoformat(),
            "tz": "UTC",
        }
        try:
            resp = http.get(f"{base_url.rstrip('/')}/weather", params=params, timeout=20)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("weather for %s failed: %s", p.name, exc)
            continue
        sink.write_raw(weather_blob_path(p.group_eva, now), resp.content)
        record = to_record(p, hour, resp.json(), now)
        if record:
            rows.append(record)
    if rows:
        sink.ingest("WeatherHourly", rows)
        sink.flush()
    return len(rows)


def load_station_list(http: httpx.Client, models_base_url: str) -> dict[str, Any]:
    resp = http.get(f"{models_base_url.rstrip('/')}/stations/stations.json", timeout=30)
    resp.raise_for_status()
    data: dict[str, Any] = json.loads(resp.content)
    return data

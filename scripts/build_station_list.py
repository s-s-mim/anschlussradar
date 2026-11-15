"""Build stations.json for the station search from GTFS timetable files.

  python scripts/build_station_list.py fv.zip rv.zip --out data/stations.json

Input: GTFS zips, by default the long-distance and regional rail feeds from gtfs.de
(DELFI data). Output: one entry per station with name, coordinates and a size rank
from the number of departures, merged across feeds.

  {"generated_at": "...", "stations": [{"id": "s1a2b3c4d5e", "name": "Frankfurt(Main)Hbf",
    "lat": 50.107, "lon": 8.663, "rank": 1.0}, ...]}

The weekly 'stations' workflow runs this and uploads the file to the public models
container, where the API reads it at start-up.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anschlussradar.api.stations import departures_rank, normalize  # noqa: E402

MERGE_DISTANCE_KM = 1.0


@dataclass
class Candidate:
    name: str
    lat: float
    lon: float
    departures: int


def _rows(zf: zipfile.ZipFile, name: str):  # type: ignore[no-untyped-def]
    with zf.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def read_feed(path: Path) -> list[Candidate]:
    with zipfile.ZipFile(path) as zf:
        stops = list(_rows(zf, "stops.txt"))
        parent_of = {s["stop_id"]: (s.get("parent_station") or "").strip() for s in stops}
        counts: Counter[str] = Counter()
        if "stop_times.txt" in zf.namelist():
            for row in _rows(zf, "stop_times.txt"):
                stop_id = row["stop_id"]
                counts[parent_of.get(stop_id) or stop_id] += 1

    out: list[Candidate] = []
    for s in stops:
        is_station = (s.get("location_type") or "0").strip() == "1"
        is_lone_stop = not parent_of.get(s["stop_id"]) and (
            s.get("location_type") or "0"
        ).strip() in ("0", "")
        if not (is_station or is_lone_stop):
            continue
        n = counts.get(s["stop_id"], 0)
        if n == 0:
            continue
        out.append(Candidate(s["stop_name"].strip(), float(s["stop_lat"]), float(s["stop_lon"]), n))
    return out


def _km(a: Candidate, b: Candidate) -> float:
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon) * math.cos(math.radians((a.lat + b.lat) / 2))
    return 6371.0 * math.hypot(dlat, dlon)


def merge(candidates: list[Candidate]) -> list[Candidate]:
    """Same normalized name within 1 km = one station; departures are added up."""
    merged: dict[str, list[Candidate]] = {}
    for c in sorted(candidates, key=lambda c: -c.departures):
        group = merged.setdefault(normalize(c.name), [])
        for existing in group:
            if _km(existing, c) <= MERGE_DISTANCE_KM:
                existing.departures += c.departures
                break
        else:
            group.append(Candidate(c.name, c.lat, c.lon, c.departures))
    return [c for group in merged.values() for c in group]


def station_id(c: Candidate) -> str:
    """Stable id from normalized name and rounded position."""
    key = f"{normalize(c.name)}|{c.lat:.2f}|{c.lon:.2f}"
    return "s" + hashlib.sha1(key.encode()).hexdigest()[:10]


def build(paths: list[Path]) -> dict[str, object]:
    stations = merge([c for p in paths for c in read_feed(p)])
    stations.sort(key=lambda c: -c.departures)
    top = stations[0].departures if stations else 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [p.name for p in paths],
        "stations": [
            {
                "id": station_id(c),
                "name": c.name,
                "lat": round(c.lat, 6),
                "lon": round(c.lon, 6),
                "rank": departures_rank(c.departures, top),
            }
            for c in stations
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("feeds", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/stations.json"))
    args = parser.parse_args()
    doc = build(args.feeds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"wrote {len(doc['stations'])} stations to {args.out}")  # type: ignore[arg-type]
    return 0 if doc["stations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

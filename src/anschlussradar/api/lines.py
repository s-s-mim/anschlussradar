"""Line pages: punctuality of regional and S-Bahn lines at the recorded stations.

A line is category + line + operator, because "S1" runs in Frankfurt, Munich and
Berlin. Data comes from Data Explorer (kql/09_lines.kql), last 28 days, cached for
an hour. Only recorded stations appear, so a line page shows the part of the line
that runs through them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from .board import hourly
from .stations import HubMatcher

log = logging.getLogger(__name__)
Rows = list[dict[str, Any]]
DAYS = 28


def line_id(category: str, line: str, operator: str) -> str:
    return hashlib.sha1(f"{category}|{line}|{operator}".encode()).hexdigest()[:10]


def line_name(category: str, line: str) -> str:
    """'S1' and 'U4' without a space, 'RE 30' with one; never 'S S1'."""
    if line.upper().startswith(category.upper()):
        return line
    return f"{category}{line}" if category in ("S", "U") else f"{category} {line}"


def _kql(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _share(on_time: int, n: int) -> float | None:
    return round(on_time / n, 3) if n >= 20 else None


def _list(value: Any) -> list[Any]:
    if isinstance(value, str):
        return list(json.loads(value or "[]"))
    return list(value or [])


class Lines:
    def __init__(self, run: Callable[[str], Rows], hubs: HubMatcher, ttl: float = 3600.0) -> None:
        self.run, self.hubs, self.ttl = run, hubs, ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: str, load: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        value = load()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def _group(self, eva: int) -> int:
        for _, h in self.hubs.hubs:
            if h.eva == eva:
                return h.group_eva
        return eva

    def _load_lines(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self.run(f"LineList({DAYS})"):
            c, ln, op = str(r["category"]), str(r["line"]), str(r.get("operator") or "")
            ends = sorted(_list(r.get("terminals")), key=lambda t: -int(t["n"]))
            n = int(r["departures"])
            out.append({
                "id": line_id(c, ln, op),
                "category": c,
                "line": ln,
                "operator": op,
                "name": line_name(c, ln),
                "terminals": [str(t["d"]) for t in ends[:2] if t.get("d")],
                "departures": n,
                "onTime": _share(int(r["on_time"]), n),
                "stations": sorted({self._group(int(e)) for e in _list(r.get("evas"))}),
            })  # fmt: skip
        order = {"S": 0, "IRE": 1, "RE": 2, "RB": 3, "U": 4}
        out.sort(
            key=lambda x: (
                order.get(x["category"], 9),
                x["category"],
                len(x["line"]),
                x["line"],
                x["terminals"],
            )
        )
        return out

    def lines(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = self._cached("lines", self._load_lines)
        return result

    def public_lines(self) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in x.items() if k not in ("operator", "stations")} for x in self.lines()
        ]

    def find(self, lid: str) -> dict[str, Any] | None:
        return next((x for x in self.lines() if x["id"] == lid), None)

    def line_for(self, category: str | None, line: str | None, group_eva: int) -> str | None:
        """The line page for a departure on a station board, if there is one."""
        if not category or not line:
            return None
        for x in self.lines():
            if x["category"] == category and x["line"] == line and group_eva in x["stations"]:
                return str(x["id"])
        return None

    def detail(self, lid: str) -> dict[str, Any] | None:
        found = self.find(lid)
        if found is None:
            return None
        info = found

        def load() -> dict[str, Any]:
            args = (
                f"{_kql(info['category'])}, {_kql(info['line'])}, {_kql(info['operator'])}, {DAYS}"
            )
            groups: dict[int, dict[str, Any]] = {}
            for r in self.run(f"LineStations({args})"):
                g = self._group(int(r["eva"]))
                n = int(r["departures"])
                cur = groups.setdefault(
                    g,
                    {"departures": 0, "on_time": 0, "cancelled": 0, "delay_sum": 0.0, "pos": None},
                )
                cur["departures"] += n
                cur["on_time"] += int(r["on_time"])
                cur["cancelled"] += int(r["cancelled"])
                ran = n - int(r["cancelled"])
                if r.get("avg_delay") not in (None, ""):
                    cur["delay_sum"] += float(r["avg_delay"]) * ran
                if r.get("pos") not in (None, ""):
                    p = float(r["pos"])
                    cur["pos"] = p if cur["pos"] is None else min(cur["pos"], p)
            names = {g: main.name for g, (main, _) in self.hubs.groups().items()}
            stations = []
            for g, v in groups.items():
                ran = v["departures"] - v["cancelled"]
                stations.append({
                    "eva": g,
                    "name": names.get(g, str(g)),
                    "departures": v["departures"],
                    "onTime": _share(v["on_time"], v["departures"]),
                    "cancelled": v["cancelled"],
                    "avgDelay": round(v["delay_sum"] / ran, 1) if ran else None,
                    "_pos": v["pos"],
                })  # fmt: skip
            # Stations without a position (only served in the other direction) go last.
            stations.sort(key=lambda s: (s["_pos"] is None, s["_pos"] or 0, s["name"]))
            for s in stations:
                del s["_pos"]
            return {
                "stations": stations,
                "hourly": hourly(self.run(f"LineHourly({args})")),
            }

        body: dict[str, Any] = self._cached(f"line:{lid}", load)
        public = {k: v for k, v in info.items() if k not in ("operator", "stations")}
        return {**public, "days": DAYS, **body}

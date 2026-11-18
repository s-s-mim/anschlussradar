"""Station names: normalization, typo-tolerant search and matching to recorded hubs.

  index = StationIndex.from_json(data)
  index.search("Franfurt hbf")  -> Frankfurt (Main) Hbf first

The same normalization is used for search and for matching Transitous stop names
to the hubs in config/hubs.csv, so "Frankfurt(Main)Hbf", "Frankfurt (Main) Hbf"
and "Frankfurt am Main Hauptbahnhof" are all the same station.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ..ingest.hubs import Hub

_UMLAUTS = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"))
# Whole-word replacements after punctuation is removed.
_WORDS = {
    "hauptbahnhof": "hbf",
    "ffm": "frankfurt main",
    "bahnhof": "bf",
    "sankt": "st",
}


def normalize(name: str) -> str:
    """Lower case, umlauts spelled out, punctuation removed, common words unified."""
    s = name.lower()
    for a, b in _UMLAUTS:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bam main\b", "main", s)
    s = re.sub(r"\ba m\b", "main", s)  # "Frankfurt a.M."
    tokens = [_WORDS.get(t, t) for t in s.split()]
    s = " ".join(" ".join(tokens).split())
    # "Frankfurt (Main)" is what everyone means by Frankfurt; other Frankfurts keep
    # their suffix ("frankfurt oder"). This makes "Frankfurt Hbf (tief)" and
    # "Frankfurt(Main)Hbf tief" the same name.
    return re.sub(r"\bfrankfurt main\b", "frankfurt", s)


def _token_similarity(query_token: str, name_token: str) -> float:
    """1.0 for a prefix (the user is still typing), otherwise a fuzzy ratio.

    Compared against the start of the name token, so 'frank' matches 'frankfurt'
    and 'franfurt' (one letter missing) still scores high.
    """
    if name_token.startswith(query_token):
        return 1.0
    head = name_token[: len(query_token) + 1]
    return SequenceMatcher(None, query_token, head).ratio()


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    name: str
    lat: float
    lon: float
    rank: float = 0.0  # 0..1, larger stations higher
    norm: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "lat": self.lat, "lon": self.lon}

    @property
    def place(self) -> str:
        """Place string for Transitous: 'lat,lon'."""
        return f"{self.lat:.6f},{self.lon:.6f}"


class StationIndex:
    MIN_TOKEN_SCORE = 0.6
    MIN_SCORE = 0.55

    def __init__(self, stations: Iterable[Station]) -> None:
        self.stations = [
            s if s.norm else Station(s.id, s.name, s.lat, s.lon, s.rank, normalize(s.name))
            for s in stations
        ]
        self.by_id = {s.id: s for s in self.stations}

    @classmethod
    def from_json(cls, data: bytes | str | dict[str, Any]) -> StationIndex:
        doc = json.loads(data) if isinstance(data, bytes | str) else data
        return cls(
            Station(
                str(s["id"]), s["name"], float(s["lat"]), float(s["lon"]), float(s.get("rank", 0))
            )
            for s in doc["stations"]
        )

    def score(self, query_norm: str, station: Station) -> float:
        name = station.norm
        if not query_norm:
            return 0.0
        if name.startswith(query_norm):
            base = 1.0
        else:
            q_tokens, n_tokens = query_norm.split(), name.split()
            per_token = [max(_token_similarity(q, n) for n in n_tokens) for q in q_tokens]
            if min(per_token) < self.MIN_TOKEN_SCORE:
                return 0.0
            token_score = sum(per_token) / len(per_token)
            whole = SequenceMatcher(None, query_norm, name).ratio()
            base = 0.75 * token_score + 0.25 * whole
        # Equally close matches: the larger station first.
        return base + 0.05 * station.rank

    def search(self, query: str, limit: int = 8) -> list[Station]:
        q = normalize(query)
        scored = [(self.score(q, s), s) for s in self.stations]
        hits = [(sc, s) for sc, s in scored if sc >= self.MIN_SCORE]
        hits.sort(key=lambda pair: (-pair[0], len(pair[1].name)))
        return [s for _, s in hits[:limit]]

    def nearby(
        self, lat: float, lon: float, limit: int = 5, max_m: float = 3000
    ) -> list[tuple[Station, int]]:
        """Closest stations with their distance in metres (as the crow flies)."""
        out = []
        for s in self.stations:
            # Cheap box test first; 0.05 degrees is about 3.5 to 5.5 km in Germany.
            if abs(s.lat - lat) > 0.05 or abs(s.lon - lon) > 0.08:
                continue
            d = distance_m(lat, lon, s.lat, s.lon)
            if d <= max_m:
                out.append((s, round(d)))
        out.sort(key=lambda pair: pair[1])
        return out[:limit]


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


@dataclass(frozen=True, slots=True)
class HubMatch:
    eva: int
    group_eva: int
    name: str


class HubMatcher:
    """Maps a stop name from Transitous to a recorded hub (EVA and station group).

    Only recorded hubs have history, so only they need matching. Exact normalized
    names first; then a strict fuzzy match, so a wrong hub is never guessed.
    """

    MIN_RATIO = 0.9

    def __init__(self, hubs: Iterable[Hub]) -> None:
        self.hubs = [(normalize(h.name), h) for h in hubs]
        self.exact = {norm: h for norm, h in self.hubs}

    def groups(self) -> dict[int, tuple[Hub, list[int]]]:
        """Station groups: group EVA -> (the main hub, every EVA of the group)."""
        out: dict[int, tuple[Hub, list[int]]] = {}
        for _, h in self.hubs:
            main, evas = out.get(h.group_eva, (h, []))
            if h.eva == h.group_eva:
                main = h
            out[h.group_eva] = (main, [*evas, h.eva])
        return out

    def match(self, stop_name: str | None) -> HubMatch | None:
        if not stop_name:
            return None
        norm = normalize(stop_name)
        hub = self.exact.get(norm)
        if hub is None:
            best_ratio, best = 0.0, None
            for hub_norm, h in self.hubs:
                ratio = SequenceMatcher(None, norm, hub_norm).ratio()
                if ratio > best_ratio:
                    best_ratio, best = ratio, h
            hub = best if best_ratio >= self.MIN_RATIO else None
        return HubMatch(hub.eva, hub.group_eva, hub.name) if hub else None


def departures_rank(count: int, max_count: int) -> float:
    """0..1 on a log scale, so mid-size stations are not all squeezed near zero."""
    if count <= 0 or max_count <= 1:
        return 0.0
    return round(math.log1p(count) / math.log1p(max_count), 4)

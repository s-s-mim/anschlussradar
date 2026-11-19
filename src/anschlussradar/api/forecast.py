"""Delay forecast for departures at recorded hubs.

Stage 1 (now): the empirical distribution of the last 4 weeks. For a train
number at a station: the median ("usually") and the 80th percentile ("on bad
days") of its departure delay, and the share of departures 6 or more minutes
late. Trains seen fewer than 3 times fall back to all trains of the same type
at that station and hour.

Stage 2 (planned): a LightGBM quantile model with weather and the time of year.
It has to beat this baseline on held-out weeks before it replaces it, the same
champion/challenger rule as the transfer model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ..ml.features import category_group
from .refresh import Refresh

log = logging.getLogger(__name__)
BERLIN = ZoneInfo("Europe/Berlin")
MIN_TRIPS = 5  # below this the app shows nothing


@dataclass(frozen=True, slots=True)
class DelayForecast:
    typical: int  # minutes, median
    high: int  # minutes, 80th percentile
    late_share: float  # share of departures 6+ minutes late
    trips: int
    basis: str  # 'train' or 'group'

    def to_dict(self) -> dict[str, Any]:
        return {
            "typical": self.typical,
            "high": self.high,
            "lateShare": round(self.late_share, 2),
            "trips": self.trips,
            "basis": self.basis,
        }


class ForecastProvider(Protocol):
    def forecast(
        self, eva: int, number: str | None, category: str | None, departure: datetime
    ) -> DelayForecast | None: ...


class NoForecast:
    def forecast(self, *args: Any, **kwargs: Any) -> DelayForecast | None:
        return None


def _fc(r: dict[str, Any], basis: str) -> DelayForecast:
    trips = int(r["trips"])
    return DelayForecast(
        typical=round(float(r["p50"])),
        high=round(float(r["p80"])),
        late_share=int(r["late"]) / trips if trips else 0.0,
        trips=trips,
        basis=basis,
    )


class KustoForecast:
    def __init__(
        self, query: Callable[[], list[dict[str, Any]]], refresh_s: float = 3600.0
    ) -> None:
        self.query = query
        self.refresh_s = refresh_s
        self._train: dict[tuple[int, str], DelayForecast] = {}
        self._group: dict[tuple[int, str, int], DelayForecast] = {}
        self._refresher = Refresh(self._load, refresh_s, "delay statistics")

    def load_rows(self, rows: list[dict[str, Any]]) -> None:
        train: dict[tuple[int, str], DelayForecast] = {}
        group: dict[tuple[int, str, int], DelayForecast] = {}
        for r in rows:
            if r["row_kind"] == "train":
                train[(int(r["eva"]), str(r["number"]))] = _fc(r, "train")
            else:
                key = (int(r["eva"]), category_group(str(r["category"])), int(r["hour"]))
                old = group.get(key)
                # Several DB categories map to one group: keep the one with most trips.
                if old is None or int(r["trips"]) > old.trips:
                    group[key] = _fc(r, "group")
        self._train, self._group = train, group

    def _load(self) -> None:
        self.load_rows(self.query())

    def _refresh(self) -> None:
        self._refresher.ensure()

    def warm(self) -> None:
        self._refresher.warm()

    def forecast(
        self, eva: int, number: str | None, category: str | None, departure: datetime
    ) -> DelayForecast | None:
        self._refresh()
        fc = self._train.get((eva, number)) if number else None
        if (fc is None or fc.trips < MIN_TRIPS) and category:
            hour = departure.astimezone(BERLIN).hour
            fc = self._group.get((eva, category_group(category), hour))
        return fc if fc is not None and fc.trips >= MIN_TRIPS else None

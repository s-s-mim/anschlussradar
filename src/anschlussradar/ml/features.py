"""Feature definitions shared by training and the API.

This module is the single source of truth for every feature. Training builds its
matrix by calling feature_vector() row by row, and the API calls the same function
per request, so production features are computed exactly as in training.

The category groups, buffer buckets and minimum transfer times are also needed in
Data Explorer. scripts/gen_kql_shared.py renders them into kql/00_shared.kql, and a
test checks that the KQL file is up to date.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

FEATURE_VERSION = 1
BERLIN = ZoneInfo("Europe/Berlin")

# Train categories as sent by the DB API ('c' in the trip label).
CATEGORY_GROUPS: dict[str, tuple[str, ...]] = {
    "long": ("ICE", "IC", "EC", "ECE", "RJ", "RJX", "NJ", "EN", "FLX", "TGV", "ES"),
    "regional": ("RE", "RB", "IRE", "MEX", "ERB", "RS", "FEX"),
    "sbahn": ("S",),
}
GROUPS: tuple[str, ...] = ("long", "regional", "sbahn", "other")

# Minimum time needed to change trains, in minutes.
MIN_TRANSFER_LONG = 5
MIN_TRANSFER_DEFAULT = 3
# Extra minutes when arrival and departure are on different levels of one station,
# e.g. S-Bahn (tief) to long-distance platforms. An assumption: compare with DB's
# official transfer times for the hubs and adjust.
CROSS_LEVEL_EXTRA_MIN = 2
MAX_BUFFER_MIN = 30

# (lowest minute, highest minute, label). Transfers outside 3..30 minutes are not modeled.
BUFFER_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (3, 4, "03-04"),
    (5, 6, "05-06"),
    (7, 9, "07-09"),
    (10, 14, "10-14"),
    (15, 30, "15-30"),
)

# Shrinkage: how many observations the prior is worth.
EXACT_PRIOR_WEIGHT = 10.0
GROUP_PRIOR_WEIGHT = 20.0
DEFAULT_GLOBAL_RATE = 0.8
# History window for the count features, in days before the service day.
HISTORY_DAYS = 56

FEATURE_NAMES: tuple[str, ...] = (
    "planned_buffer_min",
    "slack_min",
    "hour",
    "weekday",
    "is_weekend",
    *(f"in_{g}" for g in GROUPS),
    *(f"out_{g}" for g in GROUPS),
    "exact_rate",
    "exact_log_n",
    "group_rate",
    "group_log_n",
)


def category_group(category: str | None) -> str:
    c = (category or "").strip().upper()
    for group, categories in CATEGORY_GROUPS.items():
        if c in categories:
            return group
    return "other"


def min_transfer_minutes(
    in_category: str | None, out_category: str | None, cross_level: bool = False
) -> int:
    base = (
        MIN_TRANSFER_LONG
        if "long" in (category_group(in_category), category_group(out_category))
        else MIN_TRANSFER_DEFAULT
    )
    return base + (CROSS_LEVEL_EXTRA_MIN if cross_level else 0)


def buffer_bucket(minutes: int) -> str:
    for low, high, label in BUFFER_BUCKETS:
        if low <= minutes <= high:
            return label
    return "outside"


def kql_weekday(moment: datetime) -> int:
    """Weekday as Data Explorer's dayofweek(): 0 = Sunday ... 6 = Saturday, German time."""
    return (moment.astimezone(BERLIN).weekday() + 1) % 7


@dataclass(frozen=True, slots=True)
class TransferInput:
    planned_buffer_min: int
    min_transfer_min: int
    hour: int  # local hour of the planned arrival
    weekday: int  # 0 = Sunday ... 6 = Saturday
    in_group: str
    out_group: str

    @classmethod
    def from_trains(
        cls,
        arr_pt: datetime,
        dep_pt: datetime,
        in_category: str | None,
        out_category: str | None,
        cross_level: bool = False,
    ) -> TransferInput:
        """Build the input for one possible transfer, as the API does per request.

        cross_level: arrival and departure EVAs differ but belong to one station group.
        """
        return cls(
            planned_buffer_min=round((dep_pt - arr_pt).total_seconds() / 60),
            min_transfer_min=min_transfer_minutes(in_category, out_category, cross_level),
            hour=arr_pt.astimezone(BERLIN).hour,
            weekday=kql_weekday(arr_pt),
            in_group=category_group(in_category),
            out_group=category_group(out_category),
        )


@dataclass(frozen=True, slots=True)
class HistoryCounts:
    """Outcomes seen in the HISTORY_DAYS before the service day.

    exact: this transfer (station, arriving train number, departing train number)
    group: similar transfers (station, both category groups, buffer bucket)
    """

    exact_made: float = 0.0
    exact_n: float = 0.0
    group_made: float = 0.0
    group_n: float = 0.0
    global_rate: float = DEFAULT_GLOBAL_RATE


def shrunk_rates(h: HistoryCounts) -> tuple[float, float]:
    """Return (group rate, exact rate), each pulled toward the level above it.

    With few observations the prior dominates; with many, the observed rate does.
    """
    group_rate = (h.group_made + GROUP_PRIOR_WEIGHT * h.global_rate) / (
        h.group_n + GROUP_PRIOR_WEIGHT
    )
    exact_rate = (h.exact_made + EXACT_PRIOR_WEIGHT * group_rate) / (h.exact_n + EXACT_PRIOR_WEIGHT)
    return group_rate, exact_rate


def _one_hot(group: str) -> list[float]:
    g = group if group in GROUPS else "other"
    return [1.0 if g == x else 0.0 for x in GROUPS]


def feature_vector(t: TransferInput, h: HistoryCounts) -> list[float]:
    group_rate, exact_rate = shrunk_rates(h)
    values = [
        float(t.planned_buffer_min),
        float(t.planned_buffer_min - t.min_transfer_min),
        float(t.hour),
        float(t.weekday),
        1.0 if t.weekday in (0, 6) else 0.0,
        *_one_hot(t.in_group),
        *_one_hot(t.out_group),
        exact_rate,
        math.log1p(h.exact_n),
        group_rate,
        math.log1p(h.group_n),
    ]
    assert len(values) == len(FEATURE_NAMES)
    return values


def confidence_label(n_observations: float) -> str:
    """How much data stands behind a score: shown next to the percentage."""
    if n_observations < 10:
        return "limited"
    if n_observations < 50:
        return "medium"
    return "high"

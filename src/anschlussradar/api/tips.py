"""Tips that turn scores into a decision.

earlier:  the requested connection is risky; a train up to an hour earlier gets
          there with a much better chance. Costs one extra journey search, made
          only when the first connection is risky.
transfer: another connection in the same result arrives at about the same time
          but changes at a station where it works more often.

Both need learned scores, so they stay silent while the model stage is live_only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .journeys import Journey

BERLIN = ZoneInfo("Europe/Berlin")
RISKY = 0.75  # below this a connection gets a tip if a better one exists
GAIN = 0.15  # a tip must be at least 15 points better ...
GOOD = 0.85  # ... and good in absolute terms
SAME_ARRIVAL = timedelta(minutes=10)
EARLIER_WINDOW = timedelta(minutes=60)


def _hhmm(t: datetime | None) -> str | None:
    return t.astimezone(BERLIN).strftime("%H:%M") if t else None


def _first_dep(j: Journey) -> datetime | None:
    leg = next((leg for leg in j.legs if leg.transit), None)
    return leg.dep_planned if leg else j.departure


def _stations(j: Journey) -> set[str]:
    return {t.station for t in j.transfers if t.station}


def _better(r_new: float | None, r_old: float) -> bool:
    return r_new is not None and r_new >= max(GOOD, r_old + GAIN)


def transfer_tips(journeys: list[Journey]) -> None:
    for j in journeys:
        r = j.reliability
        if r is None or r >= RISKY or not j.transfers or j.arrival is None:
            continue
        options = [
            k
            for k in journeys
            if k is not j
            and k.arrival is not None
            and abs(k.arrival - j.arrival) <= SAME_ARRIVAL
            and _better(k.reliability, r)
            and _stations(k) != _stations(j)
        ]
        if not options:
            continue
        best = max(options, key=lambda k: k.reliability or 0.0)
        station = next(iter(sorted(_stations(best))), None)
        j.tips.append(tip("transfer", best, r, station=station))


def earliest(journeys: list[Journey]) -> Journey | None:
    timed = [j for j in journeys if _first_dep(j) is not None]
    return min(timed, key=lambda j: _first_dep(j)) if timed else None  # type: ignore[arg-type, return-value]


def needs_earlier(journeys: list[Journey]) -> Journey | None:
    """The requested (first) connection, if it is risky enough to look earlier."""
    first = earliest(journeys)
    if first is None or first.reliability is None or first.reliability >= RISKY:
        return None
    return first


def earlier_tip(target: Journey, candidates: list[Journey]) -> None:
    dep, r = _first_dep(target), target.reliability
    if dep is None or r is None or target.arrival is None:
        return
    options = [
        k
        for k in candidates
        if (k_dep := _first_dep(k)) is not None
        and dep - EARLIER_WINDOW <= k_dep < dep
        and k.arrival is not None
        and k.arrival <= target.arrival
        and _better(k.reliability, r)
    ]
    if not options:
        return
    best = max(options, key=lambda k: _first_dep(k))  # type: ignore[arg-type, return-value]
    k_dep = _first_dep(best)
    assert k_dep is not None
    target.tips.append(tip("earlier", best, r, minutes=round((dep - k_dep).total_seconds() / 60)))


def tip(kind: str, better: Journey, old: float, **extra: Any) -> dict[str, Any]:
    dep = _first_dep(better)
    return {
        "kind": kind,
        "departure": _hhmm(dep),
        "departureIso": dep.astimezone(BERLIN).isoformat() if dep else None,
        "arrival": _hhmm(better.arrival),
        "reliability": better.reliability,
        "previous": old,
        **extra,
    }

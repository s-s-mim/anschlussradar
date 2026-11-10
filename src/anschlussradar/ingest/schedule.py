"""Decide which API calls to make in a given minute.

The free plan allows 60 requests per minute for the whole application key.
The poller keeps to its own share (default 50) and leaves the rest for
on-demand calls from the API.

Per hub:
  rchg  every 2 minutes (half of the hubs in even minutes, half in odd)
  plan  once an hour, for the next hour, at a fixed minute per hub
  fchg  once an hour, 30 minutes after the plan slot, to repair any gaps
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..db_api.client import Endpoint
from .hubs import Hub


@dataclass(frozen=True, slots=True)
class Call:
    endpoint: Endpoint
    eva: int
    plan_for: datetime | None = None  # only for PLAN


def calls_for_minute(hubs: list[Hub], moment: datetime, budget: int = 50) -> list[Call]:
    """Return the calls for the minute that contains `moment`, within `budget`.

    Plan calls come first (a missing plan makes changes unusable), then the
    hourly resync, then recent changes. If the budget is too small, the
    lowest-priority recent-change calls are dropped and picked up two
    minutes later.
    """
    minute_index = int(moment.timestamp() // 60)
    minute_of_hour = moment.minute
    next_hour = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    plans: list[Call] = []
    resyncs: list[Call] = []
    recent: list[Call] = []
    for i, hub in enumerate(hubs):
        if i % 60 == minute_of_hour:
            plans.append(Call(Endpoint.PLAN, hub.eva, plan_for=next_hour))
        if (i + 30) % 60 == minute_of_hour:
            resyncs.append(Call(Endpoint.FCHG, hub.eva))
        if i % 2 == minute_index % 2:
            recent.append(Call(Endpoint.RCHG, hub.eva))

    calls = plans + resyncs + recent
    return calls[:budget]


def bootstrap_calls(hubs: list[Hub], moment: datetime) -> list[Call]:
    """Calls for a cold start: plans for this hour and the next, plus full changes.

    Run once after deployment or after an outage. 3 calls per hub, so 80 hubs
    take about 5 minutes at 50 calls per minute; the rate limiter spreads them.
    """
    this_hour = moment.replace(minute=0, second=0, microsecond=0)
    out: list[Call] = []
    for hub in hubs:
        out.append(Call(Endpoint.PLAN, hub.eva, plan_for=this_hour))
        out.append(Call(Endpoint.PLAN, hub.eva, plan_for=this_hour + timedelta(hours=1)))
        out.append(Call(Endpoint.FCHG, hub.eva))
    return out

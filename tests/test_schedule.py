from collections import Counter
from datetime import UTC, datetime, timedelta

from anschlussradar.db_api.client import Endpoint
from anschlussradar.ingest.hubs import Hub
from anschlussradar.ingest.schedule import bootstrap_calls, calls_for_minute

HUBS = [Hub(eva=8000000 + i, name=f"Hub {i}", state="HE", priority=1) for i in range(80)]
START = datetime(2026, 11, 4, 7, 0, tzinfo=UTC)


def _hour_of_calls() -> list:
    calls = []
    for m in range(60):
        calls += calls_for_minute(HUBS, START + timedelta(minutes=m))
    return calls


def test_never_exceeds_budget() -> None:
    for m in range(120):
        assert len(calls_for_minute(HUBS, START + timedelta(minutes=m), budget=50)) <= 50


def test_every_hub_gets_one_plan_and_one_resync_per_hour() -> None:
    calls = _hour_of_calls()
    plans = Counter(c.eva for c in calls if c.endpoint is Endpoint.PLAN)
    resyncs = Counter(c.eva for c in calls if c.endpoint is Endpoint.FCHG)
    assert set(plans.values()) == {1} and len(plans) == 80
    assert set(resyncs.values()) == {1} and len(resyncs) == 80


def test_every_hub_gets_recent_changes_every_two_minutes() -> None:
    calls = _hour_of_calls()
    recent = Counter(c.eva for c in calls if c.endpoint is Endpoint.RCHG)
    assert set(recent.values()) == {30}


def test_plan_is_for_next_hour() -> None:
    calls = calls_for_minute(HUBS, START.replace(minute=5))
    plan = next(c for c in calls if c.endpoint is Endpoint.PLAN)
    assert plan.plan_for == START + timedelta(hours=1)


def test_small_budget_keeps_plans_first() -> None:
    calls = calls_for_minute(HUBS, START, budget=2)
    assert all(c.endpoint is not Endpoint.RCHG for c in calls)


def test_bootstrap_covers_all_hubs() -> None:
    calls = bootstrap_calls(HUBS, START)
    assert len(calls) == 240

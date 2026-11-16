"""Watched connections: storing, the morning check and the push."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from anschlussradar.api.push import MemoryPusher
from anschlussradar.api.watch import MemoryWatchStore
from anschlussradar.api.watcher import check_watches, cleanup
from tests.test_api_service import PLAN, make_service

DEVICE = "0123456789abcdef0123456789abcdef"
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}
# Monday 16 Nov 2026, 06:50 UTC = 07:50 in Germany. PLAN's first journey leaves 07:32 local
# (06:32 UTC); the watch below is for that train, checked ~1 hour before.
CHECK_AT = datetime(2026, 11, 16, 5, 40, tzinfo=UTC)


def body(**change):  # type: ignore[no-untyped-def]
    return {
        "device": DEVICE, "subscription": SUB,
        "from": {"name": "Kriftel", "place": "50.084,8.469"},
        "to": {"name": "Köln Hbf", "place": "50.943,6.959"},
        "departure": "07:32", "weekdays": "12345", "lang": "de", **change,
    }  # fmt: skip


def ready(tmp_path: Path, plan=PLAN):  # type: ignore[no-untyped-def]
    svc = make_service(tmp_path, handler=lambda r: httpx.Response(200, json=plan))
    svc.watches, svc.pusher, svc.vapid_public_key = MemoryWatchStore(), MemoryPusher(), "PUB"
    return svc


def test_create_list_delete(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    status, created = svc.post_watch(body(), "1.2.3.4", now=CHECK_AT)
    assert status == 201 and created["watch"]["weekdays"] == "12345"
    assert svc.get_watches(DEVICE, now=CHECK_AT)[1]["watches"][0]["departure"] == "07:32"
    wid = created["watch"]["id"]
    assert svc.delete_watch(DEVICE, wid)[0] == 200
    assert svc.watches.get_device(DEVICE) is None  # last watch gone: device forgotten


def test_validation_and_limits(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    assert svc.post_watch(body(device="nope"), "x")[1]["error"]["field"] == "device"
    assert svc.post_watch(body(departure="7:32"), "x")[1]["error"]["field"] == "departure"
    assert svc.post_watch(body(weekdays="89"), "x")[1]["error"]["field"] == "weekdays"
    assert svc.post_watch(body(subscription={"endpoint": "http://x"}), "x")[0] == 400
    for i in range(5):
        assert svc.post_watch(body(), f"c{i}")[0] == 201
    assert svc.post_watch(body(), "c9")[0] == 409
    off = make_service(tmp_path)
    assert off.post_watch(body(), "x")[0] == 503 and off.get_push_key()[0] == 503


def test_morning_check_warns_only_when_at_risk(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    svc.post_watch(body(), "x", now=CHECK_AT)
    # Too early: nothing happens.
    assert check_watches(svc, CHECK_AT - timedelta(hours=1)).checked == 0
    # The S1 is +4 and the ICE +1 in PLAN: the change at Frankfurt is missed.
    result = check_watches(svc, CHECK_AT)
    assert (result.checked, result.alerts) == (1, 1)
    payload = svc.pusher.sent[0][1]
    assert "Frankfurt" in payload["body"] and payload["url"].startswith("/connections?")
    # Checked once per day only.
    assert check_watches(svc, CHECK_AT + timedelta(minutes=10)).checked == 0


def test_quiet_when_all_is_fine(tmp_path: Path) -> None:
    # PLAN's second journey: S1 at 07:02, 12 minutes to change, no delays reported.
    svc = ready(tmp_path, plan={"itineraries": [PLAN["itineraries"][1]]})
    svc.post_watch(body(departure="07:02"), "x", now=CHECK_AT)
    result = check_watches(svc, CHECK_AT - timedelta(minutes=30))
    assert (result.checked, result.alerts, result.not_found) == (1, 0, 0)


def test_weekend_and_gone_subscription_and_cleanup(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    svc.post_watch(body(weekdays="67"), "x", now=CHECK_AT)  # weekends only; CHECK_AT is a Monday
    assert check_watches(svc, CHECK_AT).checked == 0
    svc2 = ready(tmp_path)
    svc2.post_watch(body(), "x", now=CHECK_AT)
    svc2.pusher.gone.add(SUB["endpoint"])
    check_watches(svc2, CHECK_AT)
    assert svc2.watches.get_device(DEVICE) is None  # unsubscribed browser: data deleted
    svc3 = ready(tmp_path)
    svc3.post_watch(body(), "x", now=CHECK_AT - timedelta(days=91))
    assert cleanup(svc3, CHECK_AT) == 1 and svc3.watches.watches() == []

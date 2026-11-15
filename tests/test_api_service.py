"""The API handlers end to end, with Transitous mocked and a local model registry."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from anschlussradar.api.contact import ContactMessage, RateLimiter, validate
from anschlussradar.api.history import KustoHistory
from anschlussradar.api.journeys import NoHistory, train_label
from anschlussradar.api.service import ApiService
from anschlussradar.api.stations import HubMatcher, Station, StationIndex
from anschlussradar.api.transitous import TransitousClient
from anschlussradar.ingest.hubs import load_hubs
from anschlussradar.ml.features import FEATURE_VERSION
from anschlussradar.ml.registry import LocalStore, ModelRegistry
from anschlussradar.ml.serving import ModelHolder

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)  # 07:30 in Germany, a Monday


def leg(mode, frm, to, dep, arr, dep_rt=None, arr_rt=None, **extra):  # type: ignore[no-untyped-def]
    return {
        "mode": mode,
        "from": {"name": frm, "track": extra.pop("dep_track", None)},
        "to": {"name": to, "track": extra.pop("arr_track", None)},
        "scheduledStartTime": dep,
        "scheduledEndTime": arr,
        "startTime": dep_rt or dep,
        "endTime": arr_rt or arr,
        "realTime": dep_rt is not None or arr_rt is not None,
        **extra,
    }


# Kriftel -> Köln: S1 to Frankfurt Hbf (tief), walk, ICE 579 from Frankfurt Hbf.
PLAN = {
    "itineraries": [
        {
            "duration": 6000,
            "startTime": "2026-11-16T06:32:00Z",
            "endTime": "2026-11-16T08:12:00Z",
            "transfers": 1,
            "legs": [
                leg(
                    "SUBURBAN",
                    "Kriftel",
                    "Frankfurt(Main)Hbf tief",
                    "2026-11-16T06:32:00Z",
                    "2026-11-16T06:48:00Z",
                    "2026-11-16T06:32:00Z",
                    "2026-11-16T06:52:00Z",
                    displayName="S1",
                    arr_track="102",
                ),
                leg(
                    "WALK",
                    "Frankfurt(Main)Hbf tief",
                    "Frankfurt (Main) Hauptbahnhof",
                    "2026-11-16T06:52:00Z",
                    "2026-11-16T06:55:00Z",
                ),
                leg(
                    "HIGHSPEED_RAIL",
                    "Frankfurt (Main) Hauptbahnhof",
                    "Köln Hbf",
                    "2026-11-16T06:56:00Z",
                    "2026-11-16T08:12:00Z",
                    "2026-11-16T06:57:00Z",
                    "2026-11-16T08:13:00Z",
                    displayName="ICE 579",
                    tripShortName="579",
                    dep_track="7",
                ),
            ],
        },
        {
            "duration": 6600,
            "startTime": "2026-11-16T06:02:00Z",
            "endTime": "2026-11-16T07:52:00Z",
            "transfers": 1,
            "legs": [
                leg(
                    "SUBURBAN",
                    "Kriftel",
                    "Frankfurt(Main)Hbf tief",
                    "2026-11-16T06:02:00Z",
                    "2026-11-16T06:18:00Z",
                    displayName="S1",
                ),
                leg(
                    "HIGHSPEED_RAIL",
                    "Frankfurt (Main) Hauptbahnhof",
                    "Köln Hbf",
                    "2026-11-16T06:30:00Z",
                    "2026-11-16T07:52:00Z",
                    displayName="ICE 1027",
                ),
            ],
        },
    ]
}


def make_service(tmp_path: Path, stage: str | None = None, handler=None, email=None) -> ApiService:  # type: ignore[no-untyped-def]
    reg = ModelRegistry(LocalStore(tmp_path))
    if stage:
        reg.save_version(
            "v1",
            {
                "model.onnx": b"0.8",
                "calibration.json": b'{"x":[],"y":[]}',
                "manifest.json": json.dumps({"feature_version": FEATURE_VERSION}).encode(),
            },
        )
        reg.set_current("v1", stage)
    calls: list[httpx.Request] = []

    def default_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=PLAN)

    client = TransitousClient(
        "https://planner.example",
        "AnschlussRadar/test (+https://example.org)",
        http=httpx.Client(transport=httpx.MockTransport(handler or default_handler)),
    )
    svc = ApiService(
        stations=StationIndex(
            [
                Station("s7", "Kriftel", 50.084, 8.469, 0.3),
                Station("s5", "Köln Hbf", 50.943, 6.959, 0.95),
            ]
        ),
        hubs=HubMatcher(load_hubs(ROOT / "config" / "hubs.csv")),
        transitous=client,
        models=ModelHolder(reg, scorer_factory=lambda b: lambda rows: [float(b)] * len(rows)),
        history=NoHistory(),
        email=email,
    )
    svc.calls = calls  # type: ignore[attr-defined]
    return svc


def test_journeys_live_only_stage(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    status, body = svc.get_journeys({"from": "s7", "to": "s5", "sort": "fastest"}, now=NOW)
    assert status == 200
    assert body["stage"] == "live_only" and body["showBanner"] is True
    first = body["journeys"][0]
    assert first["arrival"].startswith("2026-11-16T08:52")  # fastest first, shown in German time
    t = body["journeys"][1]["transfers"][0]
    assert t["probability"] is None  # no model yet
    assert t["recordedHub"] is True  # S-Bahn level and ICE level are one station group
    # Live check for the delayed S1 (+4) and ICE (+1): buffer 8, minimum 5 + 2 for the level change.
    live = [j for j in body["journeys"] if j["transfers"][0]["liveStatus"]][0]["transfers"][0]
    assert live["plannedBufferMinutes"] == 8
    assert live["liveStatus"] == "missed" and live["liveSlackMinutes"] == -2


def test_journeys_with_model_scores_and_sorts(tmp_path: Path) -> None:
    svc = make_service(tmp_path, stage="early")
    status, body = svc.get_journeys({"from": "s7", "to": "s5", "sort": "reliable"}, now=NOW)
    assert status == 200 and body["stage"] == "early"
    t = body["journeys"][0]["transfers"][0]
    assert t["probability"] == pytest.approx(0.8)
    assert t["earlyEstimate"] is True and t["confidence"] == "limited"
    assert body["journeys"][0]["reliability"] == pytest.approx(0.8)


def test_transitous_request_and_cache(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    svc.get_journeys({"from": "s7", "to": "s5"}, now=NOW)
    svc.get_journeys({"from": "s7", "to": "s5"}, now=NOW)
    calls = svc.calls  # type: ignore[attr-defined]
    assert len(calls) == 1  # second search served from cache
    req = calls[0]
    assert req.url.path == "/api/v5/plan"
    assert req.url.params["fromPlace"] == "50.084000,8.469000"
    assert "HIGHSPEED_RAIL" in req.url.params["transitModes"]
    assert req.headers["User-Agent"].startswith("AnschlussRadar/")
    assert svc.transitous.usage.plan_requests == 1 and svc.transitous.usage.cache_hits == 1


def test_bad_requests(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    assert svc.get_journeys({"from": "nope", "to": "s5"}, now=NOW)[0] == 400
    assert svc.get_journeys({"from": "s7", "to": "s7"}, now=NOW)[0] == 400
    assert (
        svc.get_journeys({"from": "s7", "to": "s5", "time": "2026-11-16T07:00"}, now=NOW)[0] == 400
    )
    assert svc.get_stations("k")[0] == 400
    assert svc.get_stations("kriftl")[1]["stations"][0]["name"] == "Kriftel"


def test_planner_down_gives_502(tmp_path: Path) -> None:
    svc = make_service(tmp_path, handler=lambda r: httpx.Response(503))
    status, body = svc.get_journeys({"from": "s7", "to": "s5"}, now=NOW)
    assert status == 502 and body["error"]["code"] == "planner_unavailable"


def test_train_label() -> None:
    assert train_label({"displayName": "ICE 579"}) == ("ICE", "579")
    assert train_label({"displayName": "S1", "mode": "SUBURBAN"}) == ("S", "1")
    assert train_label({"displayName": "Some Express", "mode": "REGIONAL_FAST_RAIL"}) == (
        "RE",
        None,
    )
    assert train_label({"displayName": "RE 30", "tripShortName": "4561"}) == ("RE", "4561")


# contact ---------------------------------------------------------------------

GOOD = {
    "name": "Erika Muster",
    "topic": "feedback",
    "email": "erika@example.org",
    "message": "The transfer at Frankfurt was right.",
    "website": "",
    "openedAt": 1_000_000,
}


class FakeEmail:
    def __init__(self) -> None:
        self.sent: list[ContactMessage] = []

    def send(self, msg: ContactMessage) -> None:
        self.sent.append(msg)


def test_contact_sends_valid_message(tmp_path: Path) -> None:
    email = FakeEmail()
    svc = make_service(tmp_path, email=email)
    status, _ = svc.post_contact(GOOD, "203.0.113.5", now=1_000 + 10)
    assert status == 202 and email.sent[0].topic == "feedback"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": "E"}, "name"),
        ({"topic": "spam"}, "topic"),
        ({"email": "no-at-sign"}, "email"),
        ({"message": "short"}, "message"),
    ],
)
def test_contact_rejects_invalid_fields(tmp_path: Path, change: dict, field: str) -> None:
    svc = make_service(tmp_path, email=FakeEmail())
    status, body = svc.post_contact({**GOOD, **change}, "203.0.113.5", now=1_010)
    assert status == 400 and body["error"]["field"] == field


def test_contact_drops_bots_silently(tmp_path: Path) -> None:
    email = FakeEmail()
    svc = make_service(tmp_path, email=email)
    assert svc.post_contact({**GOOD, "website": "http://spam"}, "x", now=1_010)[0] == 202
    assert svc.post_contact(GOOD, "x", now=1_001)[0] == 202  # sent after 1 second
    assert email.sent == []


def test_contact_rate_limit(tmp_path: Path) -> None:
    svc = make_service(tmp_path, email=FakeEmail())
    svc.contact_limiter = RateLimiter(limit=2)
    results = [svc.post_contact(GOOD, "198.51.100.7", now=1_010)[0] for _ in range(3)]
    assert results == [202, 202, 429]


def test_contact_not_configured(tmp_path: Path) -> None:
    assert make_service(tmp_path).post_contact(GOOD, "x", now=1_010)[0] == 503


def test_validate_requires_open_time() -> None:
    assert validate({k: v for k, v in GOOD.items() if k != "openedAt"}, now=1_010) is None


# history ---------------------------------------------------------------------


def test_kusto_history_rows_and_failure() -> None:
    rows = [
        {
            "row_kind": "exact",
            "eva": 8000105,
            "in_number": "35128",
            "out_number": "579",
            "made": 20,
            "n": 25,
        },
        {
            "row_kind": "group",
            "eva": 8000105,
            "in_group": "sbahn",
            "out_group": "long",
            "buffer_bucket": "07-09",
            "made": 700,
            "n": 1000,
        },
        {"row_kind": "global", "made": 8000, "n": 10000},
    ]
    h = KustoHistory(lambda: rows)
    c = h.counts(8000105, "35128", "579", "sbahn", "long", "07-09")
    assert (c.exact_made, c.exact_n, c.group_n, c.global_rate) == (20, 25, 1000, 0.8)
    assert h.counts(None, "1", "2", "sbahn", "long", "07-09").exact_n == 0

    def boom():  # type: ignore[no-untyped-def]
        raise RuntimeError("cluster down")

    broken = KustoHistory(boom)
    assert broken.counts(8000105, "1", "2", "sbahn", "long", "07-09").exact_n == 0  # no crash

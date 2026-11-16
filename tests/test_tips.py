"""'Take the earlier train' and 'better transfer station'."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from anschlussradar.api.journeys import NoHistory
from anschlussradar.api.service import ApiService
from anschlussradar.api.stations import HubMatcher, Station, StationIndex
from anschlussradar.api.transitous import TransitousClient
from anschlussradar.ingest.hubs import load_hubs
from anschlussradar.ml.features import FEATURE_VERSION
from anschlussradar.ml.registry import LocalStore, ModelRegistry
from anschlussradar.ml.serving import ModelHolder
from tests.test_api_service import PLAN, ROOT, leg

NOW = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)
LATE, EARLY = PLAN["itineraries"]  # 06:32 -> 08:12 and 06:02 -> 07:52 (UTC)


def service(tmp_path: Path, scores: list[float], handler) -> ApiService:  # type: ignore[no-untyped-def]
    reg = ModelRegistry(LocalStore(tmp_path))
    reg.save_version(
        "v1",
        {
            "model.onnx": b"x",
            "calibration.json": b'{"x":[],"y":[]}',
            "manifest.json": json.dumps({"feature_version": FEATURE_VERSION}).encode(),
        },
    )
    reg.set_current("v1", "early")
    it = iter(scores)
    return ApiService(
        stations=StationIndex(
            [Station("s7", "Kriftel", 50.084, 8.469), Station("s5", "Köln Hbf", 50.943, 6.959)]
        ),
        hubs=HubMatcher(load_hubs(ROOT / "config" / "hubs.csv")),
        transitous=TransitousClient(
            "https://p.example", "test", http=httpx.Client(transport=httpx.MockTransport(handler))
        ),
        models=ModelHolder(reg, scorer_factory=lambda b: lambda rows: [next(it) for _ in rows]),
        history=NoHistory(),
    )


def test_earlier_train_when_the_requested_one_is_risky(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        earlier = req.url.params["time"] < "2026-11-16T06:00"
        return httpx.Response(200, json={"itineraries": [EARLY if earlier else LATE]})

    svc = service(tmp_path, [0.6, 0.95], handler)
    _, body = svc.get_journeys({"from": "s7", "to": "s5"}, now=NOW)
    tips = body["journeys"][0]["tips"]
    assert tips == [
        {
            "kind": "earlier",
            "departure": "07:02",
            "departureIso": "2026-11-16T07:02:00+01:00",
            "arrival": "08:52",
            "reliability": 0.95,
            "previous": 0.6,
            "minutes": 30,
        }
    ]


def test_no_tip_when_the_connection_is_fine_or_still_learning(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.params["time"])
        return httpx.Response(200, json={"itineraries": [LATE]})

    svc = service(tmp_path, [0.9], handler)
    _, body = svc.get_journeys({"from": "s7", "to": "s5"}, now=NOW)
    assert body["journeys"][0]["tips"] == [] and len(calls) == 1  # no extra search


def test_better_transfer_station_in_the_same_result(tmp_path: Path) -> None:
    via_mainz = {
        "duration": 6300, "startTime": "2026-11-16T06:40:00Z", "endTime": "2026-11-16T08:15:00Z", "transfers": 1,
        "legs": [
            leg("REGIONAL_RAIL", "Kriftel", "Mainz Hbf", "2026-11-16T06:40:00Z", "2026-11-16T07:05:00Z", displayName="RB 75"),
            leg("HIGHSPEED_RAIL", "Mainz Hbf", "Köln Hbf", "2026-11-16T07:20:00Z", "2026-11-16T08:15:00Z", displayName="ICE 27"),
        ],
    }  # fmt: skip
    svc = service(
        tmp_path,
        [0.55, 0.93, 0.5, 0.5],
        lambda r: httpx.Response(200, json={"itineraries": [LATE, via_mainz]}),
    )
    _, body = svc.get_journeys(
        {"from": "s7", "to": "s5", "time": "2026-11-16T07:35:00+01:00"}, now=NOW
    )
    risky = next(j for j in body["journeys"] if j["reliability"] == 0.55)
    kinds = [t["kind"] for t in risky["tips"]]
    assert "transfer" in kinds
    t = next(t for t in risky["tips"] if t["kind"] == "transfer")
    assert t["station"] == "Mainz Hbf" and t["reliability"] == 0.93

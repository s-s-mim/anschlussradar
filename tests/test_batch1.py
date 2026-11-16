"""Weather collection, 'Hat's geklappt?' answers and the hub lookup script."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from anschlussradar.api.feedback import MemoryFeedbackStore, validate
from anschlussradar.ingest.hubs import Hub
from anschlussradar.ingest.weather import collect, hub_places, to_record
from tests.test_api_service import make_service

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 16, 17, 7, tzinfo=UTC)
STATIONS = {
    "stations": [
        {"id": "a", "name": "Frankfurt(Main)Hbf", "lat": 50.107, "lon": 8.663},
        {"id": "b", "name": "Köln Hbf", "lat": 50.943, "lon": 6.959},
    ]
}


class RecordingSink:
    def __init__(self) -> None:
        self.raw: list[str] = []
        self.rows: dict[str, list[dict]] = {}

    def write_raw(self, path: str, data: bytes) -> None:
        self.raw.append(path)

    def ingest(self, table: str, records: list[dict]) -> None:
        self.rows.setdefault(table, []).extend(records)

    def flush(self) -> None:
        pass


def test_hub_places_uses_main_level_and_skips_unknown() -> None:
    hubs = [
        Hub(8000105, "Frankfurt (Main) Hbf", "HE", 1),
        Hub(8098105, "Frankfurt Hbf (tief)", "HE", 1, 8000105),
        Hub(8000207, "Köln Hbf", "NW", 1),
        Hub(1, "Nirgendwo Hbf", "XX", 2),
    ]
    places = hub_places(hubs, STATIONS)
    assert [p.group_eva for p in places] == [8000105, 8000207]


def test_collect_writes_the_last_full_hour() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["date"] == "2026-11-16T16:00:00+00:00"
        return httpx.Response(
            200,
            json={
                "weather": [
                    {
                        "timestamp": "2026-11-16T16:00:00+00:00",
                        "temperature": 4.2,
                        "precipitation": 0.3,
                        "wind_speed": 12.0,
                        "wind_gust_speed": 30.0,
                        "visibility": 9000,
                        "cloud_cover": 90,
                        "condition": "rain",
                        "source_id": 1234,
                    },
                    {"timestamp": "2026-11-16T17:00:00+00:00", "temperature": 4.0},
                ]
            },
        )

    hubs = [Hub(8000207, "Köln Hbf", "NW", 1)]
    sink = RecordingSink()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        n = collect(hub_places(hubs, STATIONS), sink, http, "https://weather.example", NOW)
    assert n == 1
    row = sink.rows["WeatherHourly"][0]
    assert row["eva"] == 8000207 and row["temperature"] == 4.2 and row["condition"] == "rain"
    assert sink.raw[0].startswith("weather/8000207/2026/11/16/17/")


def test_weather_record_matches_table() -> None:
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "gen_kql_tables.py")
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    place = hub_places([Hub(8000207, "Köln Hbf", "NW", 1)], STATIONS)[0]
    hour = datetime(2026, 11, 16, 16, tzinfo=UTC)
    rec = to_record(place, hour, {"weather": [{"timestamp": hour.isoformat()}]}, NOW)
    assert rec is not None
    assert set(rec) == {c for c, _ in gen.TABLES["WeatherHourly"]}


# feedback ---------------------------------------------------------------------


def answer(**change):  # type: ignore[no-untyped-def]
    dep = NOW - timedelta(minutes=30)
    body = {
        "station": "Frankfurt (Main) Hauptbahnhof",
        "inTrain": "S1",
        "outTrain": "ICE 579",
        "plannedArrival": (dep - timedelta(minutes=8)).isoformat(),
        "plannedDeparture": dep.isoformat(),
        "made": True,
    }
    return {**body, **change}


def test_feedback_is_stored_with_hub_and_without_client(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    svc.feedback = MemoryFeedbackStore()
    status, _ = svc.post_feedback(answer(), "203.0.113.9", now=NOW)
    assert status == 202
    fb = svc.feedback.items[0]
    assert fb.hub_eva == 8000105 and fb.made is True
    assert "203.0.113.9" not in json.dumps(fb.__class__.__name__ + str(fb))


def test_feedback_rejects_future_and_bad_values(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    svc.feedback = MemoryFeedbackStore()
    future = (NOW + timedelta(hours=2)).isoformat()
    assert svc.post_feedback(answer(plannedDeparture=future), "x", now=NOW)[0] == 400
    assert svc.post_feedback(answer(made="yes"), "x", now=NOW)[1]["error"]["field"] == "made"
    assert svc.post_feedback(answer(station=""), "x", now=NOW)[0] == 400
    assert make_service(tmp_path).post_feedback(answer(), "x", now=NOW)[0] == 503


def test_feedback_validate_keeps_offsets() -> None:
    fields = validate(answer(), NOW)
    assert fields["planned_departure"].endswith("+00:00")


# add_hubs script ----------------------------------------------------------------


def _add_hubs():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("add_hubs", ROOT / "scripts" / "add_hubs.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["add_hubs"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_add_hubs_picks_exact_names_only() -> None:
    mod = _add_hubs()
    xml = (
        b'<stations><station name="Augsburg Hbf" eva="8000013" ds100="MA" meta="8098013"/>'
        b'<station name="Augsburg-Oberhausen" eva="8000600" ds100="MAO"/></stations>'
    )
    found = mod.parse_stations(xml)
    hit = mod.pick("Augsburg Hbf", found)
    assert hit.eva == 8000013 and hit.meta == (8098013,)
    assert mod.pick("Augsburg Haunstetterstraße", found) is None


def test_candidates_are_not_already_hubs() -> None:
    mod = _add_hubs()
    from anschlussradar.api.stations import normalize
    from anschlussradar.ingest.hubs import load_hubs

    have = {normalize(h.name) for h in load_hubs(ROOT / "config" / "hubs.csv")}
    candidates = mod.read_candidates(ROOT / "config" / "hub_candidates.csv")
    assert len(candidates) == 42
    assert not [c["name"] for c in candidates if normalize(c["name"]) in have]

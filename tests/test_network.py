"""The network map endpoint: station groups, coordinates and punctuality windows."""

from pathlib import Path

from anschlussradar.api.network import NetworkStatus
from anschlussradar.api.stations import Station, StationIndex
from tests.test_api_service import make_service


def test_network_sums_station_levels_and_hides_thin_windows(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    queries: list[str] = []

    def run(q: str) -> list[dict]:
        queries.append(q)
        return [
            # Frankfurt Hbf and its S-Bahn level count as one station.
            {"eva": 8000105, "week_departures": 900, "week_on_time": 720, "week_cancelled": 9,
             "now_departures": 20, "now_on_time": 15, "now_cancelled": 1},
            {"eva": 8098105, "week_departures": 100, "week_on_time": 80, "week_cancelled": 1,
             "now_departures": 3, "now_on_time": 3, "now_cancelled": 0},
            {"eva": 8000207, "week_departures": 500, "week_on_time": 400, "week_cancelled": 2,
             "now_departures": 2, "now_on_time": 1, "now_cancelled": 0},
        ]  # fmt: skip

    stations = StationIndex([
        Station("a", "Frankfurt(Main)Hbf", 50.107, 8.663, 1.0),
        Station("b", "Köln Hbf", 50.943, 6.959, 0.95),
        Station("c", "Paris Gare de l'Est", 48.876, 2.359, 0.9),
    ])  # fmt: skip
    svc.network = NetworkStatus(run, svc.hubs, stations)
    status, body = svc.get_network()
    assert status == 200 and body["available"] is True
    by_eva = {s["eva"]: s for s in body["stations"]}
    ffm = by_eva[8000105]
    assert ffm["week"] == {"departures": 1000, "onTime": 0.8, "cancelled": 10}
    assert ffm["now"]["onTime"] == round(18 / 23, 3)
    assert abs(ffm["lat"] - 50.107) < 0.01  # from the station list
    assert by_eva[8000207]["now"]["onTime"] is None  # 2 departures are too few to judge
    # Stations missing from the station list are left out, not placed at 0,0.
    assert all(s["lat"] and s["lon"] for s in body["stations"])
    svc.get_network()
    assert queries == ["NetworkStatus()"]  # cached


def test_network_unavailable(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    assert svc.get_network() == (200, {"available": False, "stations": []})
    svc.network = NetworkStatus(lambda q: 1 / 0, svc.hubs, svc.stations)  # type: ignore[arg-type,return-value]
    assert svc.get_network()[0] == 502

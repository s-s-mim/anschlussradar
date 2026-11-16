"""Line pages: the line list, one line's stations in order, links from the board."""

from datetime import UTC, datetime
from pathlib import Path

from anschlussradar.api.board import StationBoards
from anschlussradar.api.lines import Lines, line_id, line_name
from tests.test_api_service import make_service

S1_FFM = ("S", "1", "DB Regio S-Bahn Rhein-Main")


def runner(queries: list[str]):  # type: ignore[no-untyped-def]
    def run(q: str) -> list[dict]:
        queries.append(q)
        if q.startswith("LineList"):
            return [
                {"category": "S", "line": "1", "operator": S1_FFM[2], "departures": 2000,
                 "on_time": 1800, "cancelled": 20, "evas": [8098105, 8000150],
                 "terminals": [{"d": "Ober-Roden", "n": 900}, {"d": "Wiesbaden Hbf", "n": 950}]},
                # Another S1 in Munich: same name, different line.
                {"category": "S", "line": "1", "operator": "S-Bahn München", "departures": 800,
                 "on_time": 700, "cancelled": 3, "evas": [8098263], "terminals": "[]"},
                {"category": "RE", "line": "30", "operator": "DB Regio", "departures": 300,
                 "on_time": 240, "cancelled": 2, "evas": [8000105, 8003200], "terminals": []},
            ]  # fmt: skip
        if q.startswith("LineStations"):
            assert '"S", "1", "DB Regio S-Bahn Rhein-Main", 28' in q
            return [
                {"eva": 8000150, "departures": 500, "on_time": 400, "cancelled": 10, "avg_delay": 3.0, "pos": 9.0},
                # Frankfurt Hbf (tief) is reported under the main station's group.
                {"eva": 8098105, "departures": 600, "on_time": 540, "cancelled": 0, "avg_delay": 1.5, "pos": 4.0},
            ]  # fmt: skip
        if q.startswith("LineHourly"):
            return [{"hour": 7, "departures": 120, "on_time": 90, "cancelled": 1}]
        if q.startswith("StationBoard"):
            return [{"eva": 8098105, "category": "S", "number": "35128", "line": "1",
                     "destination": "Wiesbaden Hbf", "dep_pt": "2026-11-16T06:40:00Z"}]  # fmt: skip
        return []

    return run


def test_line_names() -> None:
    assert line_name("S", "1") == "S1"
    assert line_name("RE", "30") == "RE 30"
    assert line_name("S", "S8") == "S8"


def test_line_list_and_detail(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    queries: list[str] = []
    svc.lines = Lines(runner(queries), svc.hubs)
    status, body = svc.get_lines()
    assert status == 200
    names = [(x["name"], x["terminals"]) for x in body["lines"]]
    assert ("S1", ["Wiesbaden Hbf", "Ober-Roden"]) in names and len(body["lines"]) == 3
    assert "operator" not in body["lines"][0]

    lid = line_id(*S1_FFM)
    status, line = svc.get_line(lid)
    assert status == 200 and line["name"] == "S1" and line["days"] == 28
    assert [s["eva"] for s in line["stations"]] == [8000105, 8000150]  # running order
    ffm = line["stations"][0]
    assert ffm["name"] == "Frankfurt (Main) Hbf" and ffm["onTime"] == 0.9 and ffm["avgDelay"] == 1.5
    assert line["hourly"][7]["onTime"] == 0.75
    assert svc.get_line("nope")[0] == 404
    svc.get_line(lid)
    assert sum(q.startswith("LineStations") for q in queries) == 1  # cached


def test_board_links_departures_to_their_line(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    queries: list[str] = []
    svc.lines = Lines(runner(queries), svc.hubs)
    svc.boards = StationBoards(runner(queries))
    status, board = svc.get_station_board(8000105, now=datetime(2026, 11, 16, 6, 30, tzinfo=UTC))
    assert status == 200
    assert board["departures"][0]["lineId"] == line_id(*S1_FFM)  # Frankfurt's S1, not Munich's

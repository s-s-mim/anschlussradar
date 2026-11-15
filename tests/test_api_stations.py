import json
import zipfile
from pathlib import Path

import pytest

from anschlussradar.api.stations import HubMatcher, Station, StationIndex, normalize
from anschlussradar.ingest.hubs import load_hubs

ROOT = Path(__file__).resolve().parents[1]

STATIONS = StationIndex(
    [
        Station("s1", "Frankfurt(Main)Hbf", 50.107, 8.663, 1.0),
        Station("s2", "Frankfurt(Main)Süd", 50.099, 8.686, 0.8),
        Station("s3", "Frankfurt(Oder)", 52.336, 14.546, 0.5),
        Station("s4", "Frankenthal Hbf", 49.535, 8.353, 0.4),
        Station("s5", "Köln Hbf", 50.943, 6.959, 0.95),
        Station("s6", "München Hbf", 48.140, 11.558, 0.95),
        Station("s7", "Kriftel", 50.084, 8.469, 0.3),
        Station("s8", "Kreiensen", 51.853, 9.968, 0.3),
    ]
)


@pytest.mark.parametrize(
    ("query", "first"),
    [
        ("Franfurt hbf", "Frankfurt(Main)Hbf"),
        ("Koeln", "Köln Hbf"),
        ("köln", "Köln Hbf"),
        ("Muenchen", "München Hbf"),
        ("Ffm Süd", "Frankfurt(Main)Süd"),
        ("Kriftl", "Kriftel"),
        ("frank", "Frankfurt(Main)Hbf"),  # still typing: largest first
        ("Frankfurt Hauptbahnhof", "Frankfurt(Main)Hbf"),
    ],
)
def test_search_examples_from_the_documentation(query: str, first: str) -> None:
    hits = STATIONS.search(query)
    assert hits, query
    assert hits[0].name == first


def test_search_does_not_return_unrelated_stations() -> None:
    names = [s.name for s in STATIONS.search("Franfurt hbf")]
    assert "Frankfurt(Main)Süd" not in names
    assert "Frankenthal Hbf" not in names


def test_normalize_unifies_spellings() -> None:
    assert normalize("Frankfurt (Main) Hbf") == normalize("Frankfurt am Main Hauptbahnhof")
    assert normalize("Frankfurt(Main)Hbf tief") == normalize("Frankfurt Hbf (tief)")
    assert normalize("Frankfurt (Oder)") == "frankfurt oder"


def test_hub_matcher_finds_levels_and_groups() -> None:
    matcher = HubMatcher(load_hubs(ROOT / "config" / "hubs.csv"))
    tief = matcher.match("Frankfurt(Main)Hbf tief")
    main = matcher.match("Frankfurt (Main) Hauptbahnhof")
    assert tief is not None and main is not None
    assert (tief.eva, tief.group_eva) == (8098105, 8000105)
    assert (main.eva, main.group_eva) == (8000105, 8000105)
    assert matcher.match("Kriftel") is None  # not a recorded hub
    assert matcher.match("Frankfurt (Oder)") is None


def test_build_station_list_from_gtfs(tmp_path: Path) -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("bsl", ROOT / "scripts" / "build_station_list.py")
    assert spec and spec.loader
    bsl = importlib.util.module_from_spec(spec)
    sys.modules["bsl"] = bsl  # dataclasses look up their module while the class is built
    spec.loader.exec_module(bsl)

    def feed(path: Path, stops: str, stop_times: str) -> Path:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("stops.txt", stops)
            zf.writestr("stop_times.txt", stop_times)
        return path

    fv = feed(
        tmp_path / "fv.zip",
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "P1,Frankfurt(Main)Hbf,50.1070,8.6630,1,\n"
        "P1a,Frankfurt(Main)Hbf,50.1071,8.6631,0,P1\n"
        "K,Köln Hbf,50.9430,6.9590,0,\n"
        "X,Nowhere,50.0,8.0,0,\n",
        "trip_id,stop_id,stop_sequence\n" + "t1,P1a,1\n" * 5 + "t1,K,2\n",
    )
    rv = feed(
        tmp_path / "rv.zip",
        "stop_id,stop_name,stop_lat,stop_lon\nF2,Frankfurt(Main)Hbf,50.1072,8.6629\nKR,Kriftel,50.084,8.469\n",
        "trip_id,stop_id,stop_sequence\n" + "t2,F2,1\n" * 3 + "t2,KR,2\n",
    )
    doc = bsl.build([fv, rv])
    names = [s["name"] for s in doc["stations"]]
    assert names[0] == "Frankfurt(Main)Hbf"  # 5 + 3 departures, merged across feeds
    assert names.count("Frankfurt(Main)Hbf") == 1
    assert "Nowhere" not in names  # no departures
    assert doc["stations"][0]["rank"] == 1.0
    index = StationIndex.from_json(json.dumps(doc))
    assert index.search("kriftl")[0].name == "Kriftel"

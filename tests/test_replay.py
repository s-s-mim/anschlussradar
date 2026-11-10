import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from anschlussradar.db_api.parser import ParseError, parse_plan
from anschlussradar.ingest.replay import replay
from anschlussradar.storage.base import raw_blob_path
from anschlussradar.storage.local import LocalSink

FIXTURES = Path(__file__).parent / "fixtures"


def test_plan_without_eva_uses_requested_eva() -> None:
    xml = (FIXTURES / "plan_no_eva.xml").read_bytes()
    stops = parse_plan(xml, 8000105)
    assert len(stops) == 3 and all(s.eva == 8000105 for s in stops)
    with pytest.raises(ParseError):
        parse_plan(xml)  # no eva anywhere


def test_replay_rebuilds_planned_stops_from_raw_files(tmp_path: Path) -> None:
    sink = LocalSink(tmp_path)
    fetched = datetime(2026, 11, 8, 17, 55, 12, 345000, tzinfo=UTC)
    sink.write_raw(raw_blob_path("plan", 8000105, fetched), (FIXTURES / "plan_no_eva.xml").read_bytes())

    files, rows, failed = replay(tmp_path / "raw", sink, "plan")
    assert (files, rows, failed) == (1, 3, 0)

    out = next((tmp_path / "tables" / "PlannedStops").glob("*.jsonl"))
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert records[0]["eva"] == 8000105
    assert records[0]["observed_at"] == "2026-11-08T17:55:12.345000+00:00"


def test_replay_recovers_file_with_trailing_bytes_and_skips_garbage(tmp_path: Path) -> None:
    import gzip

    base = tmp_path / "raw" / "db" / "plan" / "8000105" / "2026" / "11" / "08" / "17"
    base.mkdir(parents=True)
    xml = (FIXTURES / "plan_no_eva.xml").read_bytes()
    (base / "20261108T175512345Z.xml.gz").write_bytes(gzip.compress(xml) + b"\xe0\x06junk")
    (base / "20261108T175513000Z.xml.gz").write_bytes(b"not gzip at all")

    files, rows, failed = replay(tmp_path / "raw", LocalSink(tmp_path), "plan")
    assert (files, rows, failed) == (2, 3, 1)


def test_raw_paths_are_unique_within_one_millisecond() -> None:
    t = datetime(2026, 11, 8, 17, 55, 12, 345000, tzinfo=UTC)
    assert raw_blob_path("plan", 8000105, t) != raw_blob_path("plan", 8000105, t)

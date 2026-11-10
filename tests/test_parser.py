from pathlib import Path

import pytest

from anschlussradar.db_api.models import delay_minutes
from anschlussradar.db_api.parser import ParseError, parse_changes, parse_plan

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_plan_reads_all_stops() -> None:
    stops = parse_plan((FIXTURES / "plan_frankfurt.xml").read_bytes())
    assert len(stops) == 3

    ice = stops[0]
    assert ice.eva == 8000105
    assert ice.category == "ICE"
    assert ice.number == "579"
    assert ice.arr_pp == "7"
    assert ice.origin == "Hamburg-Altona"
    assert ice.destination == "München Hbf"
    assert ice.service_date == "2026-11-04"
    # 08:20 local time in November (CET, UTC+1) is 07:20 UTC
    assert ice.arr_pt is not None
    assert ice.arr_pt.utc.isoformat() == "2026-11-04T07:20:00+00:00"


def test_parse_plan_line_and_departure_only_stop() -> None:
    stops = parse_plan((FIXTURES / "plan_frankfurt.xml").read_bytes())
    s_bahn, regional = stops[1], stops[2]
    assert s_bahn.line == "1"
    assert regional.arr_pt is None
    assert regional.line == "30"
    assert regional.origin == "Frankfurt(Main)Hbf"  # starts here


def test_parse_changes_delay_platform_and_messages() -> None:
    changes = parse_changes((FIXTURES / "changes_frankfurt.xml").read_bytes())
    assert len(changes) == 3

    ice = changes[0]
    assert ice.arrival is not None and ice.arrival.cp == "9"
    assert {m.scope for m in ice.messages} == {"stop", "arrival"}
    him = next(m for m in ice.messages if m.type == "h")
    assert him.text == "Bauarbeiten zwischen Fulda und Frankfurt"
    delay_cause = next(m for m in ice.messages if m.type == "d")
    assert delay_cause.code == 31


def test_delay_is_changed_minus_planned() -> None:
    stops = {s.stop_id: s for s in parse_plan((FIXTURES / "plan_frankfurt.xml").read_bytes())}
    changes = parse_changes((FIXTURES / "changes_frankfurt.xml").read_bytes())
    ice_change = changes[0]
    ice_plan = stops[ice_change.stop_id]
    assert ice_change.arrival is not None
    assert delay_minutes(ice_plan.arr_pt, ice_change.arrival.ct) == 7


def test_cancellation_is_parsed() -> None:
    changes = parse_changes((FIXTURES / "changes_frankfurt.xml").read_bytes())
    cancelled = changes[2]
    assert cancelled.departure is not None
    assert cancelled.departure.cs == "c"
    assert cancelled.departure.clt is not None


def test_event_id_is_stable_and_content_based() -> None:
    xml = (FIXTURES / "changes_frankfurt.xml").read_bytes()
    first = [c.event_id() for c in parse_changes(xml)]
    second = [c.event_id() for c in parse_changes(xml)]
    assert first == second
    assert len(set(first)) == 3


def test_record_has_table_columns() -> None:
    from datetime import UTC, datetime

    change = parse_changes((FIXTURES / "changes_frankfurt.xml").read_bytes())[0]
    record = change.to_record(datetime(2026, 11, 4, 7, 10, tzinfo=UTC), "rchg")
    for column in ("event_id", "stop_id", "eva", "arr_ct", "dep_cp", "messages", "endpoint"):
        assert column in record
    assert record["endpoint"] == "rchg"


@pytest.mark.parametrize(
    "xml", [b"", b"   ", b"<html>error</html>", b"<timetable/>", b"not xml at all"]
)
def test_bad_responses_raise_parse_error(xml: bytes) -> None:
    with pytest.raises(ParseError):
        parse_changes(xml)


def test_entities_are_not_resolved() -> None:
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<timetable station="X" eva="1"><s id="a"><m id="m1" t="f">&x;</m></s></timetable>"""
    changes = parse_changes(evil)
    assert all("root:" not in (m.text or "") for c in changes for m in c.messages)

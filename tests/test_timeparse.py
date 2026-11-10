from datetime import UTC, datetime

from anschlussradar.db_api.timeparse import TimeFlag, parse_db_time, to_db_date_hour


def test_winter_and_summer_offsets() -> None:
    winter = parse_db_time("2601151200")
    summer = parse_db_time("2607151200")
    assert winter is not None and winter.utc.hour == 11
    assert summer is not None and summer.utc.hour == 10
    assert winter.flag is TimeFlag.OK


def test_spring_forward_gap_is_flagged() -> None:
    # 29 March 2026: clocks jump from 02:00 to 03:00
    t = parse_db_time("2603290230")
    assert t is not None
    assert t.flag is TimeFlag.NONEXISTENT


def test_fall_back_overlap_is_flagged() -> None:
    # 25 October 2026: 02:00 to 02:59 happens twice
    t = parse_db_time("2610250230")
    assert t is not None
    assert t.flag is TimeFlag.AMBIGUOUS
    assert t.utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # first, summer time


def test_empty_values() -> None:
    assert parse_db_time(None) is None
    assert parse_db_time("") is None


def test_plan_date_hour_uses_german_time() -> None:
    # 23:30 UTC on 4 Nov is 00:30 on 5 Nov in Germany
    assert to_db_date_hour(datetime(2026, 11, 4, 23, 30, tzinfo=UTC)) == ("261105", "00")

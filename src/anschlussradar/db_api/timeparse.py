"""Time handling for the DB Timetables API.

The API sends local German time as 'yyMMddHHmm', e.g. '2611040742' is
4 Nov 2026, 07:42. There is no offset in the string, so two cases need care:

* Spring forward (last Sunday in March): 02:00 to 02:59 does not exist.
* Fall back (last Sunday in October): 02:00 to 02:59 happens twice.

We convert to UTC and return a flag so the data quality checks can count
these cases instead of silently storing a wrong time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
DB_TIME_FORMAT = "%y%m%d%H%M"


class TimeFlag(StrEnum):
    OK = "ok"
    NONEXISTENT = "nonexistent"  # spring forward gap, shifted forward by one hour
    AMBIGUOUS = "ambiguous"  # fall back overlap, first occurrence (summer time) chosen


@dataclass(frozen=True, slots=True)
class ParsedTime:
    utc: datetime
    flag: TimeFlag


def parse_db_time(value: str | None) -> ParsedTime | None:
    """Parse 'yyMMddHHmm' local German time. Returns None for empty input."""
    if not value:
        return None
    naive = datetime.strptime(value, DB_TIME_FORMAT)
    local = naive.replace(tzinfo=BERLIN)

    # Nonexistent local time: converting to UTC and back gives a different wall time.
    round_trip = local.astimezone(UTC).astimezone(BERLIN)
    if round_trip.replace(tzinfo=None) != naive:
        # Treat it like a clock that was not yet moved forward.
        return ParsedTime(utc=local.astimezone(UTC), flag=TimeFlag.NONEXISTENT)

    # Ambiguous local time: fold=0 and fold=1 give different UTC offsets.
    other = naive.replace(tzinfo=BERLIN, fold=1)
    if other.utcoffset() != local.utcoffset():
        return ParsedTime(utc=local.astimezone(UTC), flag=TimeFlag.AMBIGUOUS)

    return ParsedTime(utc=local.astimezone(UTC), flag=TimeFlag.OK)


def to_db_date_hour(moment: datetime) -> tuple[str, str]:
    """Return ('yyMMdd', 'HH') in German local time, as the /plan endpoint expects."""
    local = moment.astimezone(BERLIN)
    return local.strftime("%y%m%d"), local.strftime("%H")


def minutes_between(start: ParsedTime | None, end: ParsedTime | None) -> int | None:
    if start is None or end is None:
        return None
    return round((end.utc - start.utc).total_seconds() / 60)

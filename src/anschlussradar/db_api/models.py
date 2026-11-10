"""Typed records produced by the parser.

Each record has a to_record() method that returns a flat dict with the
column names of the matching Data Explorer table (see kql/01_tables.kql).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .timeparse import ParsedTime, minutes_between


def _iso(t: ParsedTime | None) -> str | None:
    return t.utc.isoformat() if t else None


def _flag(*times: ParsedTime | None) -> str:
    flags = {t.flag.value for t in times if t is not None and t.flag.value != "ok"}
    return ",".join(sorted(flags)) if flags else "ok"


@dataclass(frozen=True, slots=True)
class Message:
    """A message attached to a stop or to its arrival/departure event.

    type: 'd' delay cause, 'q' quality change, 'h' HIM disruption text, 'f' free text,
          'c' connection, and others listed in the API documentation.
    code: numeric reason code for delay and quality messages.
    """

    message_id: str
    type: str | None
    code: int | None
    category: str | None
    text: str | None
    timestamp: ParsedTime | None
    valid_from: ParsedTime | None
    valid_to: ParsedTime | None
    priority: int | None
    scope: str  # 'stop', 'arrival' or 'departure'

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "type": self.type,
            "code": self.code,
            "category": self.category,
            "text": self.text,
            "timestamp": _iso(self.timestamp),
            "valid_from": _iso(self.valid_from),
            "valid_to": _iso(self.valid_to),
            "priority": self.priority,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class PlannedStop:
    stop_id: str
    eva: int
    station_name: str
    category: str | None  # ICE, IC, RE, RB, S ...
    number: str | None
    line: str | None
    operator: str | None
    filter_flag: str | None  # 'F' long distance, 'N' regional, 'S' S-Bahn
    trip_type: str | None
    arr_pt: ParsedTime | None
    dep_pt: ParsedTime | None
    arr_pp: str | None
    dep_pp: str | None
    origin: str | None  # first station of the arrival path
    destination: str | None  # last station of the departure path
    arr_path: list[str] = field(default_factory=list)
    dep_path: list[str] = field(default_factory=list)

    @property
    def service_date(self) -> str | None:
        """Service day from the stop ID (the origin departure date), as yyyy-MM-dd."""
        parts = self.stop_id.rsplit("-", 2)
        if len(parts) == 3 and len(parts[1]) >= 6 and parts[1][:6].isdigit():
            d = parts[1][:6]
            return f"20{d[0:2]}-{d[2:4]}-{d[4:6]}"
        return None

    def to_record(self, observed_at: datetime) -> dict[str, Any]:
        return {
            "stop_id": self.stop_id,
            "eva": self.eva,
            "station_name": self.station_name,
            "service_date": self.service_date,
            "category": self.category,
            "number": self.number,
            "line": self.line,
            "operator": self.operator,
            "filter_flag": self.filter_flag,
            "trip_type": self.trip_type,
            "arr_pt": _iso(self.arr_pt),
            "dep_pt": _iso(self.dep_pt),
            "arr_pp": self.arr_pp,
            "dep_pp": self.dep_pp,
            "origin": self.origin,
            "destination": self.destination,
            "arr_path": self.arr_path,
            "dep_path": self.dep_path,
            "time_flag": _flag(self.arr_pt, self.dep_pt),
            "observed_at": observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class EventChange:
    """Changed values for an arrival or a departure."""

    ct: ParsedTime | None = None  # changed (forecast) time
    cp: str | None = None  # changed platform
    cs: str | None = None  # changed status: 'c' cancelled, 'a' added, 'p' planned
    clt: ParsedTime | None = None  # time the cancellation was created
    planned_time: ParsedTime | None = None  # only present for added trips


@dataclass(frozen=True, slots=True)
class StopChange:
    stop_id: str
    eva: int
    arrival: EventChange | None
    departure: EventChange | None
    messages: list[Message]
    # Trip label, only sent for added or replaced trips
    category: str | None = None
    number: str | None = None

    def event_id(self) -> str:
        """Deterministic ID of this exact change content.

        The same change seen in 'rchg' and later in 'fchg' gets the same ID,
        so duplicates can be removed downstream.
        """
        payload = self.to_record_content()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(canonical.encode("utf-8")).hexdigest()

    def to_record_content(self) -> dict[str, Any]:
        a = self.arrival or EventChange()
        d = self.departure or EventChange()
        return {
            "stop_id": self.stop_id,
            "eva": self.eva,
            "arr_ct": _iso(a.ct),
            "arr_cp": a.cp,
            "arr_cs": a.cs,
            "arr_clt": _iso(a.clt),
            "dep_ct": _iso(d.ct),
            "dep_cp": d.cp,
            "dep_cs": d.cs,
            "dep_clt": _iso(d.clt),
            "category": self.category,
            "number": self.number,
            "message_ids": sorted(m.message_id for m in self.messages),
        }

    def to_record(self, observed_at: datetime, endpoint: str) -> dict[str, Any]:
        a = self.arrival or EventChange()
        d = self.departure or EventChange()
        record = self.to_record_content()
        record.pop("message_ids")
        record.update(
            {
                "event_id": self.event_id(),
                "endpoint": endpoint,
                "observed_at": observed_at.isoformat(),
                "messages": [m.to_dict() for m in self.messages],
                "time_flag": _flag(a.ct, d.ct, a.clt, d.clt),
            }
        )
        return record


def delay_minutes(planned: ParsedTime | None, changed: ParsedTime | None) -> int | None:
    """Delay in minutes. None if there is no forecast (train on time or unknown)."""
    return minutes_between(planned, changed)


def as_plain_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)

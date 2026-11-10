"""Parse XML from the DB Timetables API into typed records.

Attribute names follow the API's short forms:
  tl  trip label: c category, n number, o operator, f filter flag, t trip type
  ar  arrival, dp departure
  pt  planned time, ct changed time, pp planned platform, cp changed platform
  ppth planned path ('|'-separated stations), l line
  cs  changed status (c cancelled, a added, p planned), clt cancellation time
  m   message: id, t type, c code, cat category, ts timestamp, from, to, pr priority
"""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

from .models import EventChange, Message, PlannedStop, StopChange
from .timeparse import parse_db_time

# A parser that never loads external entities or touches the network.
_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=True
)


class ParseError(ValueError):
    pass


def _root(xml: bytes | str) -> etree._Element:
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    if not data.strip():
        raise ParseError("empty response")
    try:
        root = etree.fromstring(data, parser=_SAFE_PARSER)
    except etree.XMLSyntaxError as exc:
        raise ParseError(f"invalid XML: {exc}") from exc
    if root.tag != "timetable":
        raise ParseError(f"unexpected root element <{root.tag}>")
    return root


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _path(value: str | None) -> list[str]:
    return [p for p in (value or "").split("|") if p]


def _messages(parent: etree._Element, scope: str) -> list[Message]:
    out: list[Message] = []
    for m in parent.findall("m"):
        message_id = m.get("id")
        if not message_id:
            continue
        out.append(
            Message(
                message_id=message_id,
                type=m.get("t"),
                code=_int(m.get("c")),
                category=m.get("cat"),
                # Free-text messages carry their text in attribute 'c' of type 'f' in some
                # responses; HIM messages may have child text. Keep whichever exists.
                text=(m.text or "").strip() or None,
                timestamp=parse_db_time(m.get("ts")),
                valid_from=parse_db_time(m.get("from")),
                valid_to=parse_db_time(m.get("to")),
                priority=_int(m.get("pr")),
                scope=scope,
            )
        )
    return out


def _station_eva(root: etree._Element, requested_eva: int | None) -> tuple[int, str]:
    """EVA from the response, or else the EVA we asked for.

    /plan responses carry only the station name on the root element; the EVA is
    known from the request URL, so the caller passes it in.
    """
    eva = _int(root.get("eva")) or requested_eva
    if eva is None:
        raise ParseError("timetable without eva attribute and no requested eva")
    return eva, root.get("station") or ""


def parse_plan(xml: bytes | str, eva: int | None = None) -> list[PlannedStop]:
    """Parse a /plan response: all planned stops at one station in one hour."""
    root = _root(xml)
    eva, station = _station_eva(root, eva)
    return list(_iter_plan(root, eva, station))


def _iter_plan(root: etree._Element, eva: int, station: str) -> Iterator[PlannedStop]:
    for s in root.findall("s"):
        stop_id = s.get("id")
        if not stop_id:
            continue
        tl = s.find("tl")
        ar = s.find("ar")
        dp = s.find("dp")
        arr_path = _path(ar.get("ppth")) if ar is not None else []
        dep_path = _path(dp.get("ppth")) if dp is not None else []
        line = None
        for ev in (dp, ar):
            if ev is not None and ev.get("l"):
                line = ev.get("l")
                break
        yield PlannedStop(
            stop_id=stop_id,
            eva=eva,
            station_name=station,
            category=tl.get("c") if tl is not None else None,
            number=tl.get("n") if tl is not None else None,
            line=line,
            operator=tl.get("o") if tl is not None else None,
            filter_flag=tl.get("f") if tl is not None else None,
            trip_type=tl.get("t") if tl is not None else None,
            arr_pt=parse_db_time(ar.get("pt")) if ar is not None else None,
            dep_pt=parse_db_time(dp.get("pt")) if dp is not None else None,
            arr_pp=ar.get("pp") if ar is not None else None,
            dep_pp=dp.get("pp") if dp is not None else None,
            origin=arr_path[0] if arr_path else station,
            destination=dep_path[-1] if dep_path else station,
            arr_path=arr_path,
            dep_path=dep_path,
        )


def _event_change(ev: etree._Element | None) -> EventChange | None:
    if ev is None:
        return None
    return EventChange(
        ct=parse_db_time(ev.get("ct")),
        cp=ev.get("cp"),
        cs=ev.get("cs"),
        clt=parse_db_time(ev.get("clt")),
        planned_time=parse_db_time(ev.get("pt")),
    )


def parse_changes(xml: bytes | str, eva: int | None = None) -> list[StopChange]:
    """Parse a /fchg or /rchg response: changes for stops at one station."""
    root = _root(xml)
    station_eva, _ = _station_eva(root, eva)
    out: list[StopChange] = []
    for s in root.findall("s"):
        stop_id = s.get("id")
        if not stop_id:
            continue
        # A change can belong to a stop at another station (e.g. a replacement);
        # the 's' element then carries its own eva.
        eva = _int(s.get("eva")) or station_eva
        ar = s.find("ar")
        dp = s.find("dp")
        tl = s.find("tl")
        messages = _messages(s, "stop")
        if ar is not None:
            messages += _messages(ar, "arrival")
        if dp is not None:
            messages += _messages(dp, "departure")
        out.append(
            StopChange(
                stop_id=stop_id,
                eva=eva,
                arrival=_event_change(ar),
                departure=_event_change(dp),
                messages=messages,
                category=tl.get("c") if tl is not None else None,
                number=tl.get("n") if tl is not None else None,
            )
        )
    return out

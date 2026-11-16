"""Why a train is late, and what is missing on board, as DB reason codes.

The DB Timetables API attaches messages to every stop: type 'd' is a delay reason
(code 31 = engineering work), types 'q' and 'f' are quality notes (code 85 = one
coach missing). Codes are a fixed list, so the web app translates them once into
every language it speaks; no text is translated at run time.

Only recorded hubs have messages, because only they are polled. The API loads all
current messages with one query every 2 minutes (KQL RecentTrainMessages) and
looks them up by station and train number.

Code meanings follow DB's published list as collected in the open-source IRIS
client Travel::Status::DE::IRIS by Birte Kristina Friesel; the texts are in
web/src/i18n/messages.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)

KNOWN_CODES = frozenset(range(1, 100))
# Quality notes that only cancel earlier ones and are never shown themselves.
CLEARS: dict[int, frozenset[int] | None] = {
    88: None,  # "no quality issues": clears every earlier quality note
    84: frozenset({80}),  # "coaches in the right order" clears "different order"
    89: frozenset({86, 87}),  # "reservations shown again" clears "no reservations"
}


@dataclass(frozen=True, slots=True)
class TrainMessage:
    code: int
    kind: str  # 'delay' or 'quality'

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "kind": self.kind}


def summarize(rows: list[dict[str, Any]]) -> dict[tuple[int, str], list[TrainMessage]]:
    """Rows from RecentTrainMessages -> current messages per (eva, train number).

    Delay reason: only the newest one. Quality notes: all current ones, after
    applying the clearing codes in time order.
    """
    by_stop: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        code = r.get("code")
        if code is None or int(code) not in KNOWN_CODES:
            continue
        by_stop[(int(r["eva"]), str(r["train_number"]))].append(r)

    out: dict[tuple[int, str], list[TrainMessage]] = {}
    for key, items in by_stop.items():
        items.sort(key=lambda r: _ts(r.get("sent_at")))
        delays = [r for r in items if r["msg_type"] == "d"]
        quality: dict[int, None] = {}  # ordered set
        for r in items:
            if r["msg_type"] not in ("q", "f"):
                continue
            code = int(r["code"])
            if code in CLEARS:
                cleared = CLEARS[code]
                quality = {} if cleared is None else {c: None for c in quality if c not in cleared}
            else:
                quality[code] = None
        msgs = [TrainMessage(int(delays[-1]["code"]), "delay")] if delays else []
        msgs += [TrainMessage(c, "quality") for c in quality]
        if msgs:
            out[key] = msgs
    return out


def current(messages: list[dict[str, Any]] | None) -> list[TrainMessage]:
    """The messages column of one stop -> what to show now (same rules as summarize)."""
    rows = [
        {"eva": 0, "train_number": "", "msg_type": m.get("type"), "code": m.get("code"),
         "sent_at": m.get("timestamp")}
        for m in messages or []
        if m.get("type") in ("d", "q", "f") and m.get("code") is not None
    ]  # fmt: skip
    return summarize(rows).get((0, ""), [])


def _ts(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


class MessageProvider(Protocol):
    def for_stop(self, eva: int, number: str) -> list[TrainMessage]: ...


class NoMessages:
    def for_stop(self, eva: int, number: str) -> list[TrainMessage]:
        return []


class KustoMessages:
    """All current messages, refreshed every 2 minutes. Failures keep the old state."""

    def __init__(self, query: Callable[[], list[dict[str, Any]]], refresh_s: float = 120.0) -> None:
        self.query = query
        self.refresh_s = refresh_s
        self._data: dict[tuple[int, str], list[TrainMessage]] = {}
        self._loaded_at: float | None = None
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        now = time.monotonic()
        if self._loaded_at is not None and now - self._loaded_at < self.refresh_s:
            return
        with self._lock:
            if self._loaded_at is not None and time.monotonic() - self._loaded_at < self.refresh_s:
                return
            try:
                self._data = summarize(self.query())
            except Exception:
                log.exception("could not load train messages; keeping the previous state")
            self._loaded_at = time.monotonic()

    def for_stop(self, eva: int, number: str) -> list[TrainMessage]:
        self._refresh()
        return self._data.get((eva, number), [])

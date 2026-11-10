"""Re-parse saved raw responses (bronze) into tables (silver).

This is why every response is stored before parsing: when the parser had a bug,
fix it and replay, and no data is lost.

  python -m anschlussradar.ingest.cli replay                  # timetables only (default)
  python -m anschlussradar.ingest.cli replay --endpoint rchg  # recent changes

Works on the local raw folder (data/raw). Replaying change endpoints again adds rows
that were already parsed; Data Explorer removes them later by event_id, but locally
they appear twice.
"""

from __future__ import annotations

import gzip
import logging
import zlib
from datetime import UTC, datetime
from pathlib import Path

from ..db_api.parser import ParseError, parse_changes, parse_plan
from ..storage.base import Sink

log = logging.getLogger(__name__)


def _fetched_at(path: Path) -> datetime:
    """'20261108T175512345Z-1a2b3c4d.xml.gz' -> 2026-11-08 17:55:12.345 UTC.

    Files written before the random suffix was added ('...345Z.xml.gz') work too.
    """
    stamp = path.name.split("Z")[0]
    base, millis = stamp[:15], stamp[15:] or "0"
    t = datetime.strptime(base, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return t.replace(microsecond=int(millis) * 1000)


def _read_raw(path: Path) -> bytes:
    """Decompress a raw file. If extra bytes follow the first gzip member (a file
    damaged by two overlapping writes), keep the first, complete member."""
    data = path.read_bytes()
    try:
        return gzip.decompress(data)
    except gzip.BadGzipFile:
        d = zlib.decompressobj(wbits=31)  # 31 = gzip format
        body = d.decompress(data)
        if not d.eof:
            raise
        log.warning("%s: %d extra bytes after the data, ignored", path, len(d.unused_data))
        return body


def replay(raw_root: Path, sink: Sink, endpoint: str = "plan") -> tuple[int, int, int]:
    """Return (files read, rows written, files that could not be used).

    A broken file is logged and skipped; it never stops the replay.
    """
    files = sorted((raw_root / "db" / endpoint).rglob("*.xml.gz"))
    rows = failed = 0
    for path in files:
        eva_part = path.relative_to(raw_root / "db" / endpoint).parts[0]
        eva = int(eva_part) if eva_part.isdigit() else None
        try:
            body = _read_raw(path)
            observed_at = _fetched_at(path)
        except (OSError, ValueError, zlib.error) as exc:
            failed += 1
            log.warning("%s: cannot read (%s), skipped", path, exc)
            continue
        try:
            if endpoint == "plan":
                stops = parse_plan(body, eva)
                sink.ingest("PlannedStops", [s.to_record(observed_at) for s in stops])
                rows += len(stops)
            else:
                events = parse_changes(body, eva)
                sink.ingest(
                    "StopChangeEvents", [e.to_record(observed_at, endpoint) for e in events]
                )
                rows += len(events)
        except ParseError as exc:
            failed += 1
            log.warning("%s: %s", path, exc)
    sink.flush()
    log.info("replayed %d %s files: %d rows, %d failed", len(files), endpoint, rows, failed)
    return len(files), rows, failed

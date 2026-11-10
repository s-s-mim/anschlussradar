"""Run a batch of API calls: fetch, store raw, parse, ingest, log."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from ..db_api.client import ApiResponse, Endpoint, TimetablesClient
from ..db_api.parser import ParseError, parse_changes, parse_plan
from ..storage.base import Sink, raw_blob_path
from .schedule import Call

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    run_id: str
    calls: int = 0
    ok: int = 0
    failed: int = 0
    planned_stops: int = 0
    change_events: int = 0
    errors: list[str] = field(default_factory=list)


def _fetch(client: TimetablesClient, call: Call) -> ApiResponse:
    if call.endpoint is Endpoint.PLAN:
        assert call.plan_for is not None
        return client.plan(call.eva, call.plan_for)
    if call.endpoint is Endpoint.FCHG:
        return client.full_changes(call.eva)
    return client.recent_changes(call.eva)


def _process(
    call: Call, resp: ApiResponse, sink: Sink, run_id: str
) -> tuple[int, int, dict[str, Any]]:
    """Store and parse one response. Returns (planned stops, change events, log row)."""
    planned = changes = 0
    error: str | None = None

    # Bronze first: even a response we cannot parse is kept for later replay.
    if resp.body:
        sink.write_raw(raw_blob_path(resp.endpoint.value, resp.eva, resp.fetched_at), resp.body)

    if resp.status_code == 200:
        try:
            if resp.endpoint is Endpoint.PLAN:
                stops = parse_plan(resp.body, resp.eva)
                sink.ingest("PlannedStops", [s.to_record(resp.fetched_at) for s in stops])
                planned = len(stops)
            else:
                events = parse_changes(resp.body, resp.eva)
                sink.ingest(
                    "StopChangeEvents",
                    [e.to_record(resp.fetched_at, resp.endpoint.value) for e in events],
                )
                changes = len(events)
        except ParseError as exc:
            error = f"parse: {exc}"
    elif resp.status_code == 404 and resp.endpoint is Endpoint.PLAN:
        # No planned stops in that hour (small station at night): not an error.
        pass
    else:
        error = f"http {resp.status_code}"

    row = {
        "run_id": run_id,
        "endpoint": resp.endpoint.value,
        "eva": resp.eva,
        "status_code": resp.status_code,
        "latency_ms": resp.latency_ms,
        "response_bytes": len(resp.body),
        "events_written": planned + changes,
        "error_text": error,
        "fetched_at": resp.fetched_at.isoformat(),
    }
    return planned, changes, row


def run_calls(
    calls: list[Call], client: TimetablesClient, sink: Sink, max_workers: int = 4
) -> RunSummary:
    summary = RunSummary(run_id=uuid.uuid4().hex)
    log_rows: list[dict[str, Any]] = []

    def work(call: Call) -> tuple[int, int, dict[str, Any]]:
        try:
            resp = _fetch(client, call)
        except httpx.TransportError as exc:
            return 0, 0, {
                "run_id": summary.run_id,
                "endpoint": call.endpoint.value,
                "eva": call.eva,
                "status_code": 0,
                "latency_ms": 0,
                "response_bytes": 0,
                "events_written": 0,
                "error_text": f"transport: {type(exc).__name__}",
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        return _process(call, resp, sink, summary.run_id)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for planned, changes, row in pool.map(work, calls):
            summary.calls += 1
            summary.planned_stops += planned
            summary.change_events += changes
            if row["error_text"]:
                summary.failed += 1
                summary.errors.append(f"{row['endpoint']}/{row['eva']}: {row['error_text']}")
            else:
                summary.ok += 1
            log_rows.append(row)

    sink.ingest("IngestionLog", log_rows)
    sink.flush()
    log.info(
        "run %s: %d calls, %d ok, %d failed, %d planned stops, %d change events",
        summary.run_id,
        summary.calls,
        summary.ok,
        summary.failed,
        summary.planned_stops,
        summary.change_events,
    )
    return summary

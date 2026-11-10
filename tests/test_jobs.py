"""End-to-end test of one polling run against a mocked DB API and the local sink."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from anschlussradar.config import Settings
from anschlussradar.db_api.client import Endpoint, RateLimiter, TimetablesClient
from anschlussradar.ingest.jobs import run_calls
from anschlussradar.ingest.schedule import Call
from anschlussradar.storage.local import LocalSink

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://apis.example/timetables/v1"
PLAN = (FIXTURES / "plan_frankfurt.xml").read_bytes()
CHANGES = (FIXTURES / "changes_frankfurt.xml").read_bytes()


def _settings() -> Settings:
    return Settings(DB_CLIENT_ID="id", DB_API_KEY="key", DB_BASE_URL=BASE)


def _client(handler) -> TimetablesClient:  # type: ignore[no-untyped-def]
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TimetablesClient(_settings(), http=http, limiter=RateLimiter(100))


def test_run_writes_raw_tables_and_log(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/plan/8000105/261104/09"):
            return httpx.Response(200, content=PLAN)
        if path.endswith("/rchg/8000105"):
            return httpx.Response(200, content=CHANGES)
        return httpx.Response(404, content=b"")

    calls = [
        Call(Endpoint.PLAN, 8000105, plan_for=datetime(2026, 11, 4, 8, 0, tzinfo=UTC)),
        Call(Endpoint.RCHG, 8000105),
        Call(Endpoint.RCHG, 8000207),
    ]
    sink = LocalSink(tmp_path)
    with _client(handler) as client:
        summary = run_calls(calls, client, sink)

    assert summary.calls == 3
    assert summary.planned_stops == 3
    assert summary.change_events == 3
    assert summary.failed == 1  # the 404 on rchg
    assert all(r.headers["DB-Client-Id"] == "id" for r in seen)
    assert all(r.headers["DB-Api-Key"] == "key" for r in seen)

    raw_files = list((tmp_path / "raw").rglob("*.xml.gz"))
    assert len(raw_files) == 2  # the empty 404 body is not stored
    assert gzip.decompress(raw_files[0].read_bytes()).startswith(b"<?xml")

    tables = {p.parent.name: p for p in (tmp_path / "tables").rglob("*.jsonl")}
    assert set(tables) == {"PlannedStops", "StopChangeEvents", "IngestionLog"}
    log_rows = [json.loads(line) for line in tables["IngestionLog"].read_text().splitlines()]
    assert len(log_rows) == 3
    assert sum(1 for r in log_rows if r["error_text"]) == 1


def test_retries_on_429_then_succeeds() -> None:
    responses = [httpx.Response(429), httpx.Response(200, content=CHANGES)]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    with _client(handler) as client:
        resp = client.recent_changes(8000105)
    assert resp.ok
    assert responses == []


def test_gives_up_after_three_attempts_without_raising() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    with _client(handler) as client:
        resp = client.recent_changes(8000105)
    assert resp.status_code == 503
    assert attempts == 3


def test_rate_limiter_blocks_over_limit() -> None:
    limiter = RateLimiter(limit=2, window_s=0.2)
    import time

    start = time.monotonic()
    for _ in range(3):
        limiter.acquire()
    assert time.monotonic() - start >= 0.15

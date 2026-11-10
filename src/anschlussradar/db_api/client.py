"""HTTP client for the DB Timetables API with rate limiting and retries.

Endpoints (free plan, 60 requests per minute):
  GET /plan/{evaNo}/{yyMMdd}/{HH}   planned stops for one hour
  GET /fchg/{evaNo}                 all known changes for today
  GET /rchg/{evaNo}                 changes from the last two minutes
  GET /station/{pattern}            station lookup by name or EVA
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from ..config import Settings
from .timeparse import to_db_date_hour


class Endpoint(StrEnum):
    PLAN = "plan"
    FCHG = "fchg"
    RCHG = "rchg"
    STATION = "station"


class RetryableError(Exception):
    """HTTP 429 or 5xx: worth retrying after a pause."""


@dataclass(frozen=True, slots=True)
class ApiResponse:
    endpoint: Endpoint
    eva: int | None
    url: str
    status_code: int
    body: bytes
    latency_ms: int
    fetched_at: datetime

    @property
    def ok(self) -> bool:
        return self.status_code == 200


class RateLimiter:
    """Sliding window limiter: at most `limit` calls in any 60 seconds.

    The API limit is per application key, so all threads share one limiter.
    """

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.window_s:
                    self._calls.popleft()
                if len(self._calls) < self.limit:
                    self._calls.append(now)
                    return
                wait = self.window_s - (now - self._calls[0])
            time.sleep(max(wait, 0.05))


class TimetablesClient:
    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        if not settings.db_client_id or not settings.db_api_key:
            raise ValueError("DB_CLIENT_ID and DB_API_KEY must be set")
        self._base = settings.db_base_url.rstrip("/")
        self._limiter = limiter or RateLimiter(settings.db_requests_per_minute)
        self._http = http or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._headers = {
            "DB-Client-Id": settings.db_client_id,
            "DB-Api-Key": settings.db_api_key,
            "Accept": "application/xml",
            "User-Agent": settings.user_agent,
        }

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TimetablesClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Public methods -------------------------------------------------------

    def plan(self, eva: int, moment: datetime) -> ApiResponse:
        date, hour = to_db_date_hour(moment)
        return self._get(Endpoint.PLAN, f"/plan/{eva}/{date}/{hour}", eva)

    def full_changes(self, eva: int) -> ApiResponse:
        return self._get(Endpoint.FCHG, f"/fchg/{eva}", eva)

    def recent_changes(self, eva: int) -> ApiResponse:
        return self._get(Endpoint.RCHG, f"/rchg/{eva}", eva)

    def station(self, pattern: str) -> ApiResponse:
        return self._get(Endpoint.STATION, f"/station/{quote(pattern, safe='')}", None)

    # Internals --------------------------------------------------------------

    def _get(self, endpoint: Endpoint, path: str, eva: int | None) -> ApiResponse:
        try:
            return self._get_with_retry(endpoint, path, eva)
        except RetryableError as exc:
            # All retries used up: return the last failure instead of raising,
            # so one bad station never stops a whole polling run.
            return exc.args[0]  # type: ignore[no-any-return]

    @retry(
        retry=retry_if_exception_type((RetryableError, httpx.TransportError)),
        wait=wait_random_exponential(multiplier=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get_with_retry(self, endpoint: Endpoint, path: str, eva: int | None) -> ApiResponse:
        self._limiter.acquire()
        url = f"{self._base}{path}"
        started = time.perf_counter()
        resp = self._http.get(url, headers=self._headers)
        result = ApiResponse(
            endpoint=endpoint,
            eva=eva,
            url=url,
            status_code=resp.status_code,
            body=resp.content,
            latency_ms=round((time.perf_counter() - started) * 1000),
            fetched_at=datetime.now(UTC),
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableError(result)
        return result

"""The API's handlers as plain Python: (status code, JSON body) in, no HTTP framework.

GET  /api/v1/stations?q=frankfurt
GET  /api/v1/journeys?from=<id or lat,lon>&to=...&time=<ISO>&arriveBy=false&sort=fastest|reliable&rail=true
GET  /api/v1/model/status
POST /api/v1/contact
GET  /api/v1/health
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..ml.serving import ModelHolder, model_status
from .contact import ContactError, EmailSender, RateLimiter, validate
from .journeys import HistoryProvider, build_journeys, sort_journeys
from .stations import HubMatcher, StationIndex
from .transitous import TransitousClient, TransitousError

log = logging.getLogger(__name__)
Response = tuple[int, dict[str, Any]]
_LATLON = re.compile(r"^-?\d{1,2}(\.\d+)?,-?\d{1,3}(\.\d+)?$")


def error(status: int, code: str, message: str, **extra: Any) -> Response:
    return status, {"error": {"code": code, "message": message, **extra}}


@dataclass
class ApiService:
    stations: StationIndex
    hubs: HubMatcher
    transitous: TransitousClient
    models: ModelHolder
    history: HistoryProvider
    email: EmailSender | None = None
    contact_limiter: RateLimiter = field(default_factory=RateLimiter)
    started_at: float = field(default_factory=time.time)

    # stations -------------------------------------------------------------

    def get_stations(self, q: str | None, limit: str | None = None) -> Response:
        q = (q or "").strip()
        if len(q) < 2:
            return error(400, "query_too_short", "Type at least 2 characters.")
        try:
            n = min(max(int(limit or 8), 1), 20)
        except ValueError:
            n = 8
        return 200, {"stations": [s.to_dict() for s in self.stations.search(q, n)]}

    # journeys -----------------------------------------------------------------

    def _place(self, value: str | None, name: str) -> str:
        v = (value or "").strip()
        if v in self.stations.by_id:
            return self.stations.by_id[v].place
        if _LATLON.match(v):
            return v
        raise ValueError(f"'{name}' must be a station id from /stations or 'lat,lon'.")

    def get_journeys(self, params: dict[str, str], now: datetime | None = None) -> Response:
        now = now or datetime.now(UTC)
        try:
            from_place = self._place(params.get("from"), "from")
            to_place = self._place(params.get("to"), "to")
            when = (
                datetime.fromisoformat(params["time"].replace("Z", "+00:00"))
                if params.get("time")
                else now
            )
            if when.tzinfo is None:
                raise ValueError("'time' needs a time zone, e.g. 2026-11-16T07:42:00+01:00.")
        except ValueError as exc:
            return error(400, "bad_request", str(exc))
        if from_place == to_place:
            return error(400, "same_station", "Start and destination are the same.")

        arrive_by = params.get("arriveBy", "false").lower() == "true"
        rail_only = params.get("rail", "true").lower() != "false"
        sort = params.get("sort", "fastest")
        if sort not in ("fastest", "reliable"):
            return error(400, "bad_request", "'sort' must be 'fastest' or 'reliable'.")

        try:
            plan = self.transitous.plan(from_place, to_place, when, arrive_by, rail_only)
        except TransitousError as exc:
            log.warning("journey planner failed: %s", exc)
            return error(
                502, "planner_unavailable", "The journey planner is not reachable right now."
            )

        model = self.models.get()
        journeys = build_journeys(plan, model, self.hubs, self.history, now)
        return 200, {
            "stage": model.stage.value,
            "showBanner": model.stage.value != "full",
            "journeys": [j.to_dict() for j in sort_journeys(journeys, sort)],
            "attribution": "Journey planning: Transitous (transitous.org/sources)",
        }

    # status, health, contact --------------------------------------------------

    def get_status(self) -> Response:
        return 200, model_status(self.models)

    def get_health(self) -> Response:
        usage = self.transitous.usage
        return 200, {
            "status": "ok",
            "stations": len(self.stations.stations),
            "hubs": len(self.hubs.hubs),
            "modelStage": self.models.get().stage.value,
            "transitousRequestsToday": usage.plan_requests,
            "transitousCacheHitsToday": usage.cache_hits,
            "uptimeSeconds": round(time.time() - self.started_at),
        }

    def post_contact(self, body: Any, client: str, now: float | None = None) -> Response:
        if self.email is None:
            return error(503, "contact_unavailable", "The contact form is not configured yet.")
        if not isinstance(body, dict):
            return error(400, "bad_request", "Expected a JSON object.")
        try:
            msg = validate(body, time.time() if now is None else now)
        except ContactError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        if msg is None:
            return 202, {"status": "received"}  # bots get the same answer as people
        if not self.contact_limiter.allow(client):
            return error(429, "too_many_messages", "Too many messages. Please try again later.")
        try:
            self.email.send(msg)
        except Exception:
            log.exception("could not send contact e-mail")
            return error(
                502, "send_failed", "The message could not be sent. Please try again later."
            )
        return 202, {"status": "received"}

"""The API's handlers as plain Python: (status code, JSON body) in, no HTTP framework.

GET  /api/v1/stations?q=frankfurt
GET  /api/v1/journeys?from=<id or lat,lon>&to=...&time=<ISO>&arriveBy=false&sort=fastest|reliable&rail=true
GET  /api/v1/model/status
GET  /api/v1/hubs                      recorded stations
GET  /api/v1/hubs/{eva}/board          next departures and punctuality by hour
GET  /api/v1/push/key                  public VAPID key for the browser
POST /api/v1/watches                   watch a connection (device ID + push address)
GET  /api/v1/watches/{device}          the device's watched connections
DEL  /api/v1/watches/{device}/{id}     stop watching one; DEL /watches/{device}: all
POST /api/v1/feedback   'Hat's geklappt?' after a transfer
POST /api/v1/contact    (unused by the web app for now)
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
from .board import StationBoards
from .contact import ContactError, EmailSender, RateLimiter, validate
from .feedback import MAX_PER_HOUR as FEEDBACK_PER_HOUR
from .feedback import FeedbackError, FeedbackStore, TransferFeedback
from .feedback import validate as validate_feedback
from .journeys import HistoryProvider, build_journeys, sort_journeys
from .messages import MessageProvider, NoMessages
from .push import Pusher
from .stations import HubMatcher, StationIndex
from .transitous import TransitousClient, TransitousError
from .watch import (
    MAX_WATCHES_PER_DEVICE,
    Device,
    WatchError,
    WatchStore,
    new_watch,
    valid_device,
)
from .watch import validate as validate_watch

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
    feedback: FeedbackStore | None = None
    messages: MessageProvider = field(default_factory=NoMessages)
    boards: StationBoards | None = None
    watches: WatchStore | None = None
    pusher: Pusher | None = None
    vapid_public_key: str = ""
    watch_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10))
    contact_limiter: RateLimiter = field(default_factory=RateLimiter)
    feedback_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(FEEDBACK_PER_HOUR))
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
        journeys = build_journeys(plan, model, self.hubs, self.history, now, self.messages)
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

    def get_hubs(self) -> Response:
        groups = sorted(self.hubs.groups().items(), key=lambda g: g[1][0].name)
        items = [{"eva": g, "name": main.name, "state": main.state} for g, (main, _) in groups]
        return 200, {"stations": items}

    def get_station_board(self, eva: Any, now: datetime | None = None) -> Response:
        try:
            group_eva = int(str(eva))
        except ValueError:
            return error(400, "bad_station", "The station must be a number.")
        group = self.hubs.groups().get(group_eva)
        if group is None:
            return error(404, "not_recorded", "AnschlussRadar does not record this station.")
        main, evas = group
        body: dict[str, Any] = {"eva": group_eva, "name": main.name, "departures": [], "hourly": []}
        if self.boards is None:
            return 200, {**body, "available": False}
        try:
            body["departures"] = self.boards.board(group_eva, evas, now or datetime.now(UTC))
            body["hourly"] = self.boards.hourly(group_eva, evas)
        except Exception:
            log.exception("station board failed for %s", group_eva)
            return error(502, "board_unavailable", "Departures are not available right now.")
        return 200, {**body, "available": True}

    # watched connections ---------------------------------------------------------

    def _watch_ready(self) -> Response | None:
        if self.watches is None or self.pusher is None or not self.vapid_public_key:
            return error(503, "alerts_unavailable", "Alerts are not set up yet.")
        return None

    def get_push_key(self) -> Response:
        return self._watch_ready() or (200, {"publicKey": self.vapid_public_key})

    def post_watch(self, body: Any, client: str, now: datetime | None = None) -> Response:
        if not_ready := self._watch_ready():
            return not_ready
        assert self.watches is not None
        now = now or datetime.now(UTC)
        try:
            fields = validate_watch(body)
        except WatchError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        if not self.watch_limiter.allow(client):
            return error(429, "too_many", "Too many requests. Please try again later.")
        if len(self.watches.watches(fields["device"])) >= MAX_WATCHES_PER_DEVICE:
            return error(409, "too_many_watches", "At most 5 watched connections per device.")
        self.watches.save_device(Device(fields["device"], fields["subscription"], now.isoformat()))
        watch = new_watch(fields, now)
        self.watches.save_watch(watch)
        return 201, {"watch": watch.to_public()}

    def get_watches(self, device: Any, now: datetime | None = None) -> Response:
        if not_ready := self._watch_ready():
            return not_ready
        assert self.watches is not None
        try:
            device_id = valid_device(device)
        except WatchError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        # Opening the app counts as use: the 90-day deletion clock starts again.
        self.watches.touch_device(device_id, now or datetime.now(UTC))
        return 200, {"watches": [w.to_public() for w in self.watches.watches(device_id)]}

    def delete_watch(self, device: Any, watch_id: Any) -> Response:
        if not_ready := self._watch_ready():
            return not_ready
        assert self.watches is not None
        try:
            device_id = valid_device(device)
        except WatchError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        if not self.watches.delete_watch(device_id, str(watch_id)):
            return error(404, "not_found", "No such watched connection.")
        if not self.watches.watches(device_id):
            self.watches.delete_device(device_id)  # nothing left to watch: forget the device
        return 200, {"status": "deleted"}

    def delete_device(self, device: Any) -> Response:
        if not_ready := self._watch_ready():
            return not_ready
        assert self.watches is not None
        try:
            device_id = valid_device(device)
        except WatchError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        self.watches.delete_device(device_id)
        return 200, {"status": "deleted"}

    def post_feedback(self, body: Any, client: str, now: datetime | None = None) -> Response:
        if self.feedback is None:
            return error(503, "feedback_unavailable", "Feedback is not configured yet.")
        now = now or datetime.now(UTC)
        try:
            fields = validate_feedback(body, now)
        except FeedbackError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        if not self.feedback_limiter.allow(client):
            return error(429, "too_many_answers", "Too many answers. Please try again later.")
        hub = self.hubs.match(fields["station"])
        record = TransferFeedback(
            **fields, hub_eva=hub.group_eva if hub else None, received_at=now.isoformat()
        )
        try:
            self.feedback.save(record)
        except Exception:
            log.exception("could not store feedback")
            return error(502, "store_failed", "The answer could not be saved. Please try again.")
        return 202, {"status": "received"}

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

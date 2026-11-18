"""The API's handlers as plain Python: (status code, JSON body) in, no HTTP framework.

GET  /api/v1/stations?q=frankfurt
POST /api/v1/stations/nearby          stations (or, with all, stops of every kind) near a position
POST /api/v1/places                    stations, stops and addresses for the From and To fields
POST /api/v1/journeys                  like GET /journeys, parameters in the body
GET  /api/v1/journeys?from=<id or lat,lon>&to=...&time=<ISO>&arriveBy=false&sort=fastest|reliable&rail=true
GET  /api/v1/model/status
GET  /api/v1/hubs                      recorded stations
GET  /api/v1/hubs/{eva}/board          next departures and punctuality by hour
GET  /api/v1/network                   punctuality of every recorded station (network map)
GET  /api/v1/lines                     regional and S-Bahn lines seen at recorded stations
POST /api/v1/questions                 send a question the help texts could not answer
GET  /api/v1/questions/{id}            the answer, once there is one
POST /api/v1/ask                       AI answer from the help texts (when switched on)
GET  /api/v1/lines/{id}                one line: its stations in order and punctuality by hour
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

from ..ml.serving import LoadedModel, ModelHolder, model_status
from .assistant import Assistant, DailyCap
from .board import StationBoards
from .contact import ContactError, EmailSender, RateLimiter, validate
from .feedback import MAX_PER_HOUR as FEEDBACK_PER_HOUR
from .feedback import FeedbackError, FeedbackStore, TransferFeedback
from .feedback import validate as validate_feedback
from .forecast import ForecastProvider, NoForecast
from .journeys import HistoryProvider, Journey, build_journeys, sort_journeys
from .lines import Lines
from .messages import MessageProvider, NoMessages
from .network import NetworkStatus
from .push import Pusher
from .questions import (
    QUESTIONS_DAILY_TOTAL,
    QUESTIONS_PER_DAY,
    QuestionError,
    QuestionStore,
    new_question,
    valid_id,
)
from .questions import validate as validate_question
from .stations import HubMatcher, StationIndex, distance_m, normalize
from .tips import EARLIER_WINDOW, earlier_tip, needs_earlier, transfer_tips
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
_JOURNEY_KEYS = {"from", "to", "time", "arriveBy", "sort", "rail"}


def _match_place(m: dict[str, Any]) -> dict[str, Any] | None:
    """A Transitous geocoding match as a place for the search fields."""
    try:
        lat, lon = float(m["lat"]), float(m["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    kind = {"STOP": "stop", "ADDRESS": "address"}.get(str(m.get("type")))
    if kind is None:
        return None
    name = str(m.get("name") or "")
    if kind == "address":
        street = str(m.get("street") or name)
        number = str(m.get("houseNumber") or "")
        name = f"{street} {number}" if number and not street.endswith(number) else street
    areas = [a for a in m.get("areas") or [] if isinstance(a, dict)]
    default = next((a.get("name") for a in areas if a.get("default")), None)
    detail = " ".join(x for x in (m.get("zip") if kind == "address" else None, default) if x)
    return {
        # Coordinates as the id: the planner walks from there, and nothing else is passed on.
        "id": f"{lat:.5f},{lon:.5f}",
        "name": name,
        "lat": lat,
        "lon": lon,
        "kind": kind,
        "detail": detail or None,
        "modes": [str(x) for x in m.get("modes") or []][:4],
    }


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
    network: NetworkStatus | None = None
    lines: Lines | None = None
    forecasts: ForecastProvider = field(default_factory=NoForecast)
    watches: WatchStore | None = None
    pusher: Pusher | None = None
    vapid_public_key: str = ""
    watch_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10))
    contact_limiter: RateLimiter = field(default_factory=RateLimiter)
    feedback_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(FEEDBACK_PER_HOUR))
    questions: QuestionStore | None = None
    assistant: Assistant | None = None
    # Test phase: few questions per person and per day, see QUESTIONS_PER_DAY in questions.py.
    question_limiter: RateLimiter = field(
        default_factory=lambda: RateLimiter(QUESTIONS_PER_DAY, window_s=86400.0)
    )
    question_cap: DailyCap = field(default_factory=lambda: DailyCap(QUESTIONS_DAILY_TOTAL))
    # Address and stop lookups at Transitous, per person and hour (answers are cached a day).
    lookup_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(120))
    ask_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10))
    ask_cap: DailyCap = field(default_factory=DailyCap)
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

    def post_nearby(self, body: Any, client: str = "") -> Response:
        """Stations near a position. The position comes in the request body, so it
        never appears in a URL or a request log, and it is rounded to about 100 m
        before use. Nothing about it is stored.

        With `all`, stops of every kind (bus, tram, U-Bahn) come from Transitous;
        otherwise, or if that fails, train stations from the app's own list."""
        try:
            lat = round(float(body["lat"]), 3)
            lon = round(float(body["lon"]), 3)
        except (TypeError, KeyError, ValueError):
            return error(400, "invalid_field", "Expected lat and lon.", field="position")
        if not (47.0 <= lat <= 55.2 and 5.5 <= lon <= 15.5):
            return 200, {"stations": [], "outside": True}
        if body.get("all") is True and self.lookup_limiter.allow(client or "anon"):
            try:
                found = (_match_place(m) for m in self.transitous.nearby_stops(lat, lon))
                stops = [p for p in found if p and p["kind"] == "stop"]
                for s in stops:
                    s["distanceM"] = round(distance_m(lat, lon, s["lat"], s["lon"]))
                stops = [s for s in stops if s["distanceM"] <= 3000]
                stops.sort(key=lambda s: s["distanceM"])
                if stops:
                    return 200, {"stations": stops[:6]}
            except TransitousError:
                log.warning("nearby stops lookup failed; using the train station list")
        hits = self.stations.nearby(lat, lon)
        return 200, {
            "stations": [{**s.to_dict(), "kind": "station", "distanceM": d} for s, d in hits]
        }

    def post_places(self, body: Any, client: str = "") -> Response:
        """Search for the From and To fields: train stations from the app's list, plus
        stops and addresses from Transitous (OpenStreetMap) when the list has too
        little or the person wants all modes. POST, so a typed home address never
        appears in a URL or request log."""
        if not isinstance(body, dict):
            return error(400, "invalid_field", "Expected a JSON object.", field="body")
        text = " ".join(str(body.get("text") or "").split())[:100]
        if len(text) < 2:
            return error(400, "query_too_short", "Type at least 2 characters.")
        lang = str(body.get("lang") or "de")[:5]
        everything = body.get("all") is True
        places = [{**s.to_dict(), "kind": "station"} for s in self.stations.search(text, 6)]
        wants_more = everything or len(places) < 3 or any(c.isdigit() for c in text)
        if len(text) >= 3 and wants_more and self.lookup_limiter.allow(client or "anon"):
            try:
                found = [
                    p for p in (_match_place(m) for m in self.transitous.geocode(text, lang)) if p
                ]
            except TransitousError:
                found = []
                log.warning("geocode lookup failed; showing train stations only")
            known = {normalize(p["name"]) for p in places}
            for p in found:
                if p["kind"] == "stop" and normalize(p["name"]) in known:
                    continue  # the same station, already in the list
                places.append(p)
            if any(c.isdigit() for c in text):
                # "Sodener Str. 5" is an address; keep the order otherwise.
                places.sort(key=lambda p: p["kind"] != "address")
        return 200, {"places": places[:10]}

    def post_journeys(self, body: Any, now: datetime | None = None) -> Response:
        """POST version of GET /journeys: positions and addresses stay out of URLs."""
        if not isinstance(body, dict):
            return error(400, "invalid_field", "Expected a JSON object.", field="body")
        params = {k: str(v) for k, v in body.items() if v is not None and k in _JOURNEY_KEYS}
        return self.get_journeys(params, now=now)

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
        journeys = build_journeys(
            plan, model, self.hubs, self.history, now, self.messages, self.forecasts
        )
        if model.stage.value != "live_only":
            self._add_tips(journeys, from_place, to_place, when, arrive_by, rail_only, model, now)
        return 200, {
            "stage": model.stage.value,
            "showBanner": model.stage.value != "full",
            "journeys": [j.to_dict() for j in sort_journeys(journeys, sort)],
            "attribution": "Journey planning: Transitous (transitous.org/sources)",
        }

    def _add_tips(
        self,
        journeys: list[Journey],
        from_place: str,
        to_place: str,
        when: datetime,
        arrive_by: bool,
        rail_only: bool,
        model: LoadedModel,
        now: datetime,
    ) -> None:
        transfer_tips(journeys)
        target = None if arrive_by else needs_earlier(journeys)
        if target is None:
            return
        try:
            earlier_plan = self.transitous.plan(
                from_place, to_place, when - EARLIER_WINDOW, False, rail_only
            )
        except TransitousError:
            return  # a tip is a bonus; never fail the search for it
        candidates = build_journeys(earlier_plan, model, self.hubs, self.history, now)
        earlier_tip(target, candidates)

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
            "assistant": self.assistant is not None,
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
            if self.lines is not None:
                try:
                    body["departures"] = [
                        {**d, "lineId": self.lines.line_for(d["category"], d["line"], group_eva)}
                        for d in body["departures"]
                    ]
                except Exception:
                    log.exception("line links failed")  # the board works without them
            body["hourly"] = self.boards.hourly(group_eva, evas)
        except Exception:
            log.exception("station board failed for %s", group_eva)
            return error(502, "board_unavailable", "Departures are not available right now.")
        return 200, {**body, "available": True}

    def get_network(self) -> Response:
        if self.network is None:
            return 200, {"available": False, "stations": []}
        try:
            stations = self.network.stations_status()
        except Exception:
            log.exception("network status failed")
            return error(502, "network_unavailable", "The network map is not available right now.")
        return 200, {"available": True, "stations": stations}

    def get_lines(self) -> Response:
        if self.lines is None:
            return 200, {"available": False, "lines": []}
        try:
            return 200, {"available": True, "lines": self.lines.public_lines()}
        except Exception:
            log.exception("line list failed")
            return error(502, "lines_unavailable", "Lines are not available right now.")

    def get_line(self, lid: Any) -> Response:
        if self.lines is None:
            return error(404, "unknown_line", "Unknown line.")
        try:
            body = self.lines.detail(str(lid or ""))
        except Exception:
            log.exception("line %s failed", lid)
            return error(502, "lines_unavailable", "Lines are not available right now.")
        if body is None:
            return error(404, "unknown_line", "Unknown line.")
        return 200, body

    # question box ---------------------------------------------------------------

    def post_question(self, body: Any, client: str, now: datetime | None = None) -> Response:
        if self.questions is None:
            return error(503, "questions_unavailable", "Questions are not set up yet.")
        try:
            fields = validate_question(body)
        except QuestionError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        if fields["subscription"] and self.pusher is None:
            fields["subscription"] = ""  # alerts not set up: the answer still shows in the app
        now = now or datetime.now(UTC)
        if not self.question_limiter.allow(client) or not self.question_cap.take(now):
            return error(
                429, "too_many", "Question limit reached for today.", limit=QUESTIONS_PER_DAY
            )
        q = new_question(fields, now)
        try:
            self.questions.save(q)
        except Exception:
            log.exception("could not store a question")
            return error(502, "questions_unavailable", "The question could not be saved.")
        return 201, {
            "question": q.to_public(),
            "notify": bool(q.subscription),
            "limit": QUESTIONS_PER_DAY,
        }

    def get_question(self, qid: Any) -> Response:
        if self.questions is None:
            return error(503, "questions_unavailable", "Questions are not set up yet.")
        try:
            q = self.questions.get(valid_id(qid))
        except QuestionError as exc:
            return error(404, "unknown_question", str(exc))
        if q is None:
            return error(404, "unknown_question", "Unknown question.")
        return 200, {"question": q.to_public()}

    def post_ask(self, body: Any, client: str, now: datetime | None = None) -> Response:
        if self.assistant is None:
            return 200, {"available": False, "answer": None}
        if not isinstance(body, dict):
            return error(400, "invalid_field", "Expected a JSON object.", field="body")
        try:
            fields = validate_question({"text": body.get("text"), "lang": body.get("lang")})
        except QuestionError as exc:
            return error(400, "invalid_field", str(exc), field=exc.field)
        context = str(body.get("context") or "")[:1500]
        if not self.ask_limiter.allow(client) or not self.ask_cap.take(now or datetime.now(UTC)):
            return 200, {"available": True, "answer": None, "limited": True}
        try:
            answer = self.assistant.answer(fields["text"], fields["lang"], context)
        except Exception:
            log.exception("assistant failed")
            answer = None
        return 200, {"available": True, "answer": answer}

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

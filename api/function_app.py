"""Public API Function App (Azure Functions, Python v2 model), HTTP triggers only.

Routes live under /api/v1 (see host.json routePrefix). All logic is in
src/anschlussradar/api/service.py; this file only translates HTTP. The deploy
workflow copies the shared package and config/hubs.csv next to this file.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import azure.functions as func

from anschlussradar.api.bootstrap import build_service
from anschlussradar.api.settings import get_api_settings

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
_service = None


def service():  # type: ignore[no-untyped-def]
    global _service
    if _service is None:
        _service = build_service(get_api_settings())
    return _service


def respond(result: tuple[int, dict[str, Any]], cache_seconds: int = 0) -> func.HttpResponse:
    status, body = result
    headers = {
        "Cache-Control": f"public, max-age={cache_seconds}"
        if cache_seconds and status == 200
        else "no-store"
    }
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
        charset="utf-8",
        headers=headers,
    )


@app.route(route="stations", methods=["GET"])
def stations(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_stations(req.params.get("q"), req.params.get("limit")), 86400)


@app.route(route="stations/nearby", methods=["POST"])
def stations_nearby(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    return respond(service().post_nearby(body, _client(req)))


@app.route(route="places", methods=["POST"])
def places(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    return respond(service().post_places(body, _client(req)))


@app.route(route="journeys", methods=["GET", "POST"])
def journeys(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "POST":
        # The web app posts: a position or a typed address then never shows up in a URL log.
        try:
            body = req.get_json()
        except ValueError:
            body = None
        return respond(service().post_journeys(body))
    return respond(service().get_journeys(dict(req.params)), 60)


@app.route(route="model/status", methods=["GET"])
def model_status(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_status(), 600)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_health())


@app.route(route="warm", methods=["GET"])
def warm(req: func.HttpRequest) -> func.HttpResponse:
    # The web app calls this when it opens, so the first search finds a running
    # instance with its statistics loading or loaded.
    return respond(service().warm())


@app.route(route="hubs", methods=["GET"])
def hubs(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_hubs(), 3600)


@app.route(route="hubs/{eva}/board", methods=["GET"])
def station_board(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_station_board(req.route_params.get("eva")), 60)


@app.route(route="network", methods=["GET"])
def network(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_network(), 600)


@app.route(route="lines", methods=["GET"])
def lines(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_lines(), 3600)


@app.route(route="lines/{id}", methods=["GET"])
def line(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_line(req.route_params.get("id")), 3600)


@app.route(route="push/key", methods=["GET"])
def push_key(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_push_key(), 3600)


@app.route(route="watches", methods=["POST"])
def add_watch(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    return respond(service().post_watch(body, _client(req)))


@app.route(route="watches/{device}", methods=["GET", "DELETE"])
def device_watches(req: func.HttpRequest) -> func.HttpResponse:
    device = req.route_params.get("device")
    if req.method == "DELETE":
        return respond(service().delete_device(device))
    return respond(service().get_watches(device))


@app.route(route="watches/{device}/{watch}", methods=["DELETE"])
def remove_watch(req: func.HttpRequest) -> func.HttpResponse:
    return respond(
        service().delete_watch(req.route_params.get("device"), req.route_params.get("watch"))
    )


@app.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def check_watches(timer: func.TimerRequest) -> None:
    from anschlussradar.api.watcher import check_watches as run
    from anschlussradar.api.watcher import notify_answers

    svc = service()
    result = run(svc)
    if result.checked:
        logging.info("watches checked: %s", result)
    if answered := notify_answers(svc):
        logging.info("answer notifications sent: %s", answered)


@app.timer_trigger(schedule="0 23 3 * * *", arg_name="timer", run_on_startup=False)
def cleanup_watches(timer: func.TimerRequest) -> None:
    from anschlussradar.api.watcher import cleanup, cleanup_questions

    logging.info("inactive devices deleted: %s", cleanup(service()))
    logging.info("old questions deleted: %s", cleanup_questions(service()))


def _client(req: func.HttpRequest) -> str:
    # Used only for the in-memory rate limit, hashed there, never stored.
    return (req.headers.get("x-forwarded-for") or "unknown").split(",")[0].strip()


@app.route(route="feedback", methods=["POST"])
def feedback(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    result = service().post_feedback(body, _client(req))
    if result[0] >= 500:
        logging.warning("feedback failed with %s", result[0])
    return respond(result)


@app.route(route="questions", methods=["POST"])
def post_question(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    return respond(service().post_question(body, _client(req)))


@app.route(route="questions/{id}", methods=["GET"])
def get_question(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_question(req.route_params.get("id")))


@app.route(route="ask", methods=["POST"])
def ask(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    return respond(service().post_ask(body, _client(req)))


@app.route(route="contact", methods=["POST"])
def contact(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None
    result = service().post_contact(body, _client(req))
    if result[0] >= 500:
        logging.warning("contact failed with %s", result[0])
    return respond(result)

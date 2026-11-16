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


@app.route(route="journeys", methods=["GET"])
def journeys(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_journeys(dict(req.params)), 60)


@app.route(route="model/status", methods=["GET"])
def model_status(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_status(), 600)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return respond(service().get_health())


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

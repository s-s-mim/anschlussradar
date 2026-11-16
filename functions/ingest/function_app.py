"""Ingestion Function App (Azure Functions, Python v2 programming model).

Timer triggers only; this app has no public HTTP endpoints.

  poll_db_api        every minute     plans, resyncs and recent changes for the hubs
  build_facts        every 10 minutes StopFacts and TransferFacts in Data Explorer
  run_quality_checks every 15 minutes QualityResults in Data Explorer
  collect_weather    every hour       weather at every hub (Bright Sky, DWD data)

The shared package (src/anschlussradar) and config/hubs.csv are copied next to
this file by the deploy workflow, so imports work the same locally and in Azure.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import azure.functions as func

from anschlussradar.config import get_settings
from anschlussradar.db_api.client import RateLimiter, TimetablesClient
from anschlussradar.ingest.hubs import load_hubs
from anschlussradar.ingest.jobs import run_calls
from anschlussradar.ingest.schedule import calls_for_minute
from anschlussradar.storage import make_sink

app = func.FunctionApp()

# Kept across invocations on a warm instance. The API limit is per key, so the
# poller keeps to its own share and leaves room for on-demand calls.
POLLER_BUDGET = int(os.environ.get("POLLER_BUDGET_PER_MINUTE", "50"))
_limiter = RateLimiter(POLLER_BUDGET)

FACT_COMMANDS = [
    ".set-or-append StopFacts <| AppendStopFacts()",
    """.set-or-append TransferFacts <| BuildTransferFacts(ago(15m))
    | join kind=leftanti (TransferFacts | where built_at > ago(2d) | project in_stop_id, out_stop_id)
      on in_stop_id, out_stop_id""",
]
QUALITY_COMMAND = ".set-or-append QualityResults <| RunAllChecks()"


@app.timer_trigger(schedule="0 * * * * *", arg_name="timer", run_on_startup=False, use_monitor=True)
def poll_db_api(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("poll_db_api is running late")
    settings = get_settings()
    hubs = load_hubs(settings.hubs_file)
    calls = calls_for_minute(hubs, datetime.now(UTC), budget=POLLER_BUDGET)
    sink = make_sink(settings)
    with TimetablesClient(settings, limiter=_limiter) as client:
        summary = run_calls(calls, client, sink)
    if summary.failed:
        logging.warning("failed calls: %s", "; ".join(summary.errors[:10]))


def _run_kusto(commands: list[str]) -> None:
    from azure.kusto.data import KustoClient

    from anschlussradar.storage.azure import kusto_connection

    settings = get_settings()
    client = KustoClient(kusto_connection(settings.kusto_query_uri, settings))
    for command in commands:
        client.execute_mgmt(settings.kusto_database, command)


@app.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def build_facts(timer: func.TimerRequest) -> None:
    _run_kusto(FACT_COMMANDS)
    logging.info("fact build done")


@app.timer_trigger(schedule="30 */15 * * * *", arg_name="timer", run_on_startup=False)
def run_quality_checks(timer: func.TimerRequest) -> None:
    _run_kusto([QUALITY_COMMAND])
    logging.info("quality checks done")


@app.timer_trigger(schedule="0 7 * * * *", arg_name="timer", run_on_startup=False)
def collect_weather(timer: func.TimerRequest) -> None:
    import httpx

    from anschlussradar.ingest.weather import collect, hub_places, load_station_list

    settings = get_settings()
    if not settings.models_base_url:
        logging.warning("MODELS_BASE_URL is not set; no weather collected")
        return
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(headers=headers) as http:
        places = hub_places(
            load_hubs(settings.hubs_file), load_station_list(http, settings.models_base_url)
        )
        rows = collect(
            places, make_sink(settings), http, settings.weather_base_url, datetime.now(UTC)
        )
    logging.info("weather rows written: %s of %s hubs", rows, len(places))

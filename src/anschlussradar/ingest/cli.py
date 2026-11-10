"""Run the poller from your laptop.

  python -m anschlussradar.ingest.cli once          # this minute's calls
  python -m anschlussradar.ingest.cli bootstrap     # plans and full changes for all hubs
  python -m anschlussradar.ingest.cli loop          # every minute until Ctrl+C
  python -m anschlussradar.ingest.cli station "Frankfurt Hbf"   # look up an EVA number
  python -m anschlussradar.ingest.cli replay        # re-parse saved timetable files
  python -m anschlussradar.ingest.cli replay --endpoint rchg     # or saved changes

With SINK=local (the default) everything is written under ./data.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import UTC, datetime

from ..config import get_settings
from ..db_api.client import TimetablesClient
from ..storage import make_sink
from .hubs import load_hubs
from .jobs import run_calls
from .replay import replay
from .schedule import bootstrap_calls, calls_for_minute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anschlussradar-ingest")
    parser.add_argument("command", choices=["once", "bootstrap", "loop", "station", "replay"])
    parser.add_argument("pattern", nargs="?", help="station name for the 'station' command")
    parser.add_argument("--budget", type=int, default=50, help="max calls per minute")
    parser.add_argument(
        "--endpoint", choices=["plan", "fchg", "rchg"], default="plan", help="for 'replay'"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()

    if args.command == "replay":  # needs no API key, only the saved raw files
        _, _, failed = replay(settings.local_data_dir / "raw", make_sink(settings), args.endpoint)
        return 0 if failed == 0 else 1

    with TimetablesClient(settings) as client:
        if args.command == "station":
            resp = client.station(args.pattern or "Frankfurt")
            print(resp.body.decode("utf-8", errors="replace"))
            return 0 if resp.ok else 1

        hubs = load_hubs(settings.hubs_file)
        sink = make_sink(settings)

        if args.command == "bootstrap":
            run_calls(bootstrap_calls(hubs, datetime.now(UTC)), client, sink)
            return 0

        if args.command == "once":
            summary = run_calls(calls_for_minute(hubs, datetime.now(UTC), args.budget), client, sink)
            return 0 if summary.failed == 0 else 1

        # loop: start each run at the top of a minute
        while True:
            started = datetime.now(UTC)
            run_calls(calls_for_minute(hubs, started, args.budget), client, sink)
            time.sleep(max(1.0, 60 - datetime.now(UTC).second))


if __name__ == "__main__":
    raise SystemExit(main())

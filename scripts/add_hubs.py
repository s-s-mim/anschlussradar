"""Look up the EVA numbers of new hubs with the DB API and add them to hubs.csv.

  python scripts/add_hubs.py           show what the API finds for each candidate
  python scripts/add_hubs.py --write   also append the verified ones to config/hubs.csv

A candidate is only accepted when the API returns a station whose name matches it
(same normalization as the station search), so a wrong station never gets in. The
script waits 3 seconds between calls: the poller in Azure uses the same API key.
Linked EVAs (other levels of the same station, 'meta') are printed for information.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anschlussradar.api.stations import normalize  # noqa: E402
from anschlussradar.config import get_settings  # noqa: E402
from anschlussradar.db_api.client import TimetablesClient  # noqa: E402

HUBS = ROOT / "config" / "hubs.csv"
CANDIDATES = ROOT / "config" / "hub_candidates.csv"


@dataclass(frozen=True)
class Found:
    eva: int
    name: str
    meta: tuple[int, ...]


def parse_stations(xml: bytes) -> list[Found]:
    root = etree.fromstring(xml)
    found = []
    for st in root.iter("station"):
        eva = st.get("eva")
        if not eva:
            continue
        meta = tuple(int(m) for m in (st.get("meta") or "").split("|") if m.strip().isdigit())
        found.append(Found(int(eva), st.get("name", ""), meta))
    return found


def pick(candidate: str, found: list[Found]) -> Found | None:
    """The station whose normalized name equals the candidate's, else None."""
    want = normalize(candidate)
    for f in found:
        if normalize(f.name) == want:
            return f
    return None


def read_candidates(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def existing_evas(path: Path) -> set[int]:
    with path.open(encoding="utf-8") as f:
        return {
            int(r["eva"]) for r in csv.DictReader(line for line in f if not line.startswith("#"))
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="append verified hubs to hubs.csv")
    args = parser.parse_args()

    have = existing_evas(HUBS)
    rows: list[str] = []
    problems = 0
    with TimetablesClient(get_settings()) as client:
        for i, c in enumerate(read_candidates(CANDIDATES)):
            if i:
                time.sleep(3)
            resp = client.station(c["name"])
            found = parse_stations(resp.body) if resp.ok and resp.body else []
            hit = pick(c["name"], found)
            if hit is None:
                problems += 1
                names = ", ".join(f"{f.name} ({f.eva})" for f in found[:5]) or "nothing"
                print(f"??  {c['name']}: no exact match. API returned: {names}")
                continue
            if hit.eva in have:
                print(f"--  {hit.name} ({hit.eva}) is already in hubs.csv")
                continue
            levels = f"   other levels: {', '.join(map(str, hit.meta))}" if hit.meta else ""
            print(f"ok  {hit.name} ({hit.eva}){levels}")
            rows.append(f"{hit.eva},{hit.name},{c['state']},{c['priority']},")
            have.add(hit.eva)

    if args.write and rows:
        with HUBS.open("a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        print(f"\nAdded {len(rows)} hubs to {HUBS.relative_to(ROOT)}.")
    elif rows:
        print(f"\n{len(rows)} hubs verified. Run again with --write to add them.")
    if problems:
        print(f"{problems} candidates need a look (marked ??). Fix the name in hub_candidates.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

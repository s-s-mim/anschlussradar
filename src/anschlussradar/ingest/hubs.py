"""The recording list: stations polled continuously."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Hub:
    eva: int
    name: str
    state: str
    priority: int  # 1 = national hub, 2 = regional hub, 3 = added by a saved trip
    # Stations with platforms on several levels have one EVA per level, e.g.
    # Frankfurt (Main) Hbf 8000105 and Frankfurt Hbf (tief) 8098105 for the S-Bahn.
    # Both get the same group, so transfers between the levels are found.
    group_eva: int = 0

    def __post_init__(self) -> None:
        if not self.group_eva:
            object.__setattr__(self, "group_eva", self.eva)


def load_hubs(path: Path) -> list[Hub]:
    """Read hubs.csv and return hubs sorted by priority, then EVA.

    The order matters: the scheduler assigns time slots by position, so a
    stable order keeps each hub in the same slot from run to run.
    """
    hubs: list[Hub] = []
    seen: set[int] = set()
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(line for line in f if not line.startswith("#")):
            eva = int(row["eva"])
            if eva in seen:
                raise ValueError(f"duplicate EVA {eva} in {path}")
            seen.add(eva)
            hubs.append(
                Hub(
                    eva=eva,
                    name=row["name"].strip(),
                    state=row.get("state", "").strip(),
                    priority=int(row.get("priority") or 1),
                    group_eva=int(row.get("group") or eva),
                )
            )
    evas = {h.eva for h in hubs}
    for h in hubs:
        if h.group_eva not in evas:
            raise ValueError(f"{h.name}: group {h.group_eva} is not itself in {path}")
    return sorted(hubs, key=lambda h: (h.priority, h.eva))

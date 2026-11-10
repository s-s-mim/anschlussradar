from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


def raw_blob_path(endpoint: str, eva: int | None, fetched_at: datetime) -> str:
    """Bronze path, partitioned so a backfill can list one day or one station.

    A random suffix makes every name unique: two answers for the same station in
    the same millisecond (e.g. this hour's and next hour's timetable) never collide.
    """
    t = fetched_at
    station = str(eva) if eva is not None else "none"
    return (
        f"db/{endpoint}/{station}/{t:%Y}/{t:%m}/{t:%d}/{t:%H}/"
        f"{t:%Y%m%dT%H%M%S}{t.microsecond // 1000:03d}Z-{uuid.uuid4().hex[:8]}.xml.gz"
    )


class Sink(Protocol):
    def write_raw(self, path: str, data: bytes) -> None:
        """Store an unchanged API response (the sink compresses it)."""

    def ingest(self, table: str, records: list[dict[str, Any]]) -> None:
        """Append records to a silver table."""

    def flush(self) -> None:
        """Send anything buffered."""

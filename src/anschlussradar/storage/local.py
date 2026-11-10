"""Local sink for development: files instead of Azure.

  data/raw/...              same layout as the Blob container
  data/tables/<Table>/<yyyy-MM-dd>.jsonl
"""

from __future__ import annotations

import gzip
import json
import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LocalSink:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def write_raw(self, path: str, data: bytes) -> None:
        target = self.root / "raw" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a unique temporary file, then rename: readers and other threads
        # never see a half-written or mixed file.
        tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(gzip.compress(data))
        os.replace(tmp, target)

    def ingest(self, table: str, records: list[dict[str, Any]]) -> None:
        if records:
            with self._lock:
                self._buffer[table].extend(records)

    def flush(self) -> None:
        with self._lock:
            buffered, self._buffer = self._buffer, defaultdict(list)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        for table, records in buffered.items():
            target = self.root / "tables" / table / f"{day}.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

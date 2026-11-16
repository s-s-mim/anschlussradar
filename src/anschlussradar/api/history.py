"""History counts from Data Explorer for transfer scores, cached for an hour.

Uses the KQL function TransferHistory() from kql/04_ml.kql, which applies the same
56-day window as training. One query per hour loads all counts; the API never
queries per request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from ..ml.features import DEFAULT_GLOBAL_RATE, HistoryCounts

log = logging.getLogger(__name__)


Rows = list[dict[str, Any]]


def kusto_query(
    query_uri: str,
    database: str,
    app_id: str,
    app_secret: str,
    tenant_id: str,
    query: str = "TransferHistory(now())",
) -> Callable[[], Rows]:
    """Return a function that runs one fixed query and gives the rows as dicts."""

    def run() -> Rows:
        from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

        if app_id:
            kcsb = KustoConnectionStringBuilder.with_aad_application_key_authentication(
                query_uri, app_id, app_secret, tenant_id
            )
        else:
            kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(query_uri)
        table = KustoClient(kcsb).execute_query(database, query).primary_results[0]
        cols = [c.column_name for c in table.columns]
        return [dict(zip(cols, row, strict=True)) for row in table]

    return run


class KustoHistory:
    def __init__(self, query: Callable[[], Rows], refresh_s: float = 3600.0) -> None:
        self.query = query
        self.refresh_s = refresh_s
        self._exact: dict[tuple[int, str, str], tuple[float, float]] = {}
        self._group: dict[tuple[int, str, str, str], tuple[float, float]] = {}
        self._global_rate = DEFAULT_GLOBAL_RATE
        self._loaded_at: float | None = None
        self._lock = threading.Lock()

    def load_rows(self, rows: list[dict[str, Any]]) -> None:
        exact: dict[tuple[int, str, str], tuple[float, float]] = {}
        group: dict[tuple[int, str, str, str], tuple[float, float]] = {}
        global_rate = DEFAULT_GLOBAL_RATE
        for r in rows:
            made, n = float(r["made"]), float(r["n"])
            kind = r["row_kind"]
            if kind == "exact":
                exact[(int(r["eva"]), str(r["in_number"]), str(r["out_number"]))] = (made, n)
            elif kind == "group":
                key = (int(r["eva"]), r["in_group"], r["out_group"], r["buffer_bucket"])
                group[key] = (made, n)
            elif kind == "global" and n > 0:
                global_rate = made / n
        self._exact, self._group, self._global_rate = exact, group, global_rate

    def _refresh(self) -> None:
        if self._loaded_at is not None and time.monotonic() - self._loaded_at < self.refresh_s:
            return
        with self._lock:
            if self._loaded_at is not None and time.monotonic() - self._loaded_at < self.refresh_s:
                return
            try:
                self.load_rows(self.query())
            except Exception:
                log.exception("could not load history counts; scores use the global rate")
            self._loaded_at = time.monotonic()

    def counts(
        self,
        group_eva: int | None,
        in_number: str | None,
        out_number: str | None,
        in_group: str,
        out_group: str,
        bucket: str,
    ) -> HistoryCounts:
        self._refresh()
        e_made = e_n = g_made = g_n = 0.0
        if group_eva is not None:
            if in_number and out_number:
                e_made, e_n = self._exact.get((group_eva, in_number, out_number), (0.0, 0.0))
            g_made, g_n = self._group.get((group_eva, in_group, out_group, bucket), (0.0, 0.0))
        return HistoryCounts(e_made, e_n, g_made, g_n, self._global_rate)

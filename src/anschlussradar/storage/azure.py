"""Azure sink: Blob Storage for bronze, Data Explorer queued ingestion for silver."""

from __future__ import annotations

import gzip
import io
import json
import threading
from collections import defaultdict
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoConnectionStringBuilder
from azure.kusto.data.data_format import DataFormat
from azure.kusto.ingest import IngestionProperties, QueuedIngestClient
from azure.storage.blob import BlobServiceClient, ContentSettings

from ..config import Settings

# JSON ingestion mappings created in kql/01_tables.kql, one per table.
MAPPINGS = {
    "PlannedStops": "PlannedStops_json",
    "StopChangeEvents": "StopChangeEvents_json",
    "IngestionLog": "IngestionLog_json",
}


def kusto_connection(
    uri: str, settings: Settings, interactive: bool = False
) -> KustoConnectionStringBuilder:
    if interactive:
        # Opens a browser window to sign in with your own account (the cluster owner).
        return KustoConnectionStringBuilder.with_interactive_login(uri)
    if settings.kusto_app_id:
        return KustoConnectionStringBuilder.with_aad_application_key_authentication(
            uri, settings.kusto_app_id, settings.kusto_app_secret, settings.kusto_tenant_id
        )
    # Local development: uses your `az login`.
    return KustoConnectionStringBuilder.with_az_cli_authentication(uri)


class AzureSink:
    def __init__(self, settings: Settings) -> None:
        credential = DefaultAzureCredential()
        blob_service = BlobServiceClient(settings.blob_account_url, credential=credential)
        self._container = blob_service.get_container_client(settings.blob_container)
        self._kusto = QueuedIngestClient(kusto_connection(settings.kusto_ingest_uri, settings))
        self._database = settings.kusto_database
        self._buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def write_raw(self, path: str, data: bytes) -> None:
        self._container.upload_blob(
            name=path,
            data=gzip.compress(data),
            overwrite=True,
            content_settings=ContentSettings(
                content_type="application/xml", content_encoding="gzip"
            ),
        )

    def ingest(self, table: str, records: list[dict[str, Any]]) -> None:
        if records:
            with self._lock:
                self._buffer[table].extend(records)

    def flush(self) -> None:
        """One ingestion per table per run keeps the number of small files low."""
        with self._lock:
            buffered, self._buffer = self._buffer, defaultdict(list)
        for table, records in buffered.items():
            lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
            props = IngestionProperties(
                database=self._database,
                table=table,
                data_format=DataFormat.MULTIJSON,
                ingestion_mapping_reference=MAPPINGS[table],
            )
            self._kusto.ingest_from_stream(io.BytesIO(lines.encode("utf-8")), props)

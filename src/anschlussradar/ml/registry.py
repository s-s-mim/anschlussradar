"""Model registry on plain files: a local folder, Blob Storage, or a public URL.

Layout (under the 'models' container, or data/models locally):

  transfer/versions/<version>/model.onnx         the model
  transfer/versions/<version>/calibration.json   isotonic calibration table
  transfer/versions/<version>/manifest.json      features, data range, metrics
  transfer/status.json                           report of the latest training run
  transfer/current.json                          live version and app stage

current.json is always written last. It is the only file the API trusts for
"which model is live and which stage is the app in", so a run that fails halfway
never leaves the app pointing at a half-written model.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx


class Store(Protocol):
    def read(self, path: str) -> bytes | None: ...

    def write(self, path: str, data: bytes) -> None: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, path: str) -> bytes | None:
        target = self.root / path
        return target.read_bytes() if target.exists() else None

    def write(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)  # atomic on the same file system


class BlobStore:
    """Read and write with Entra ID (used by the retrain workflow)."""

    def __init__(self, account_url: str, container: str = "models") -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self._container = service.get_container_client(container)

    def read(self, path: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._container.download_blob(path).readall()  # type: ignore[no-any-return]
        except ResourceNotFoundError:
            return None

    def write(self, path: str, data: bytes) -> None:
        # A single upload replaces a blob atomically: readers see old or new, never half.
        self._container.upload_blob(path, data, overwrite=True)


class HttpReadStore:
    """Read-only access to the public 'models' container (used by the API).

    The models are derived from open data and contain no personal data, so the
    container allows anonymous reads of single blobs (no listing).
    """

    def __init__(self, base_url: str, http: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=10.0)

    def read(self, path: str) -> bytes | None:
        resp = self._http.get(f"{self.base_url}/{path}", headers={"Cache-Control": "no-cache"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def write(self, path: str, data: bytes) -> None:
        raise PermissionError("HttpReadStore is read-only")


def new_version_id(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")


class ModelRegistry:
    def __init__(self, store: Store, name: str = "transfer") -> None:
        self.store = store
        self.name = name

    def _path(self, *parts: str) -> str:
        return "/".join((self.name, *parts))

    # versions ---------------------------------------------------------------

    def save_version(self, version: str, files: dict[str, bytes]) -> None:
        for filename, data in files.items():
            self.store.write(self._path("versions", version, filename), data)

    def read_file(self, version: str, filename: str) -> bytes | None:
        return self.store.read(self._path("versions", version, filename))

    def read_json(self, version: str, filename: str) -> dict[str, Any] | None:
        data = self.read_file(version, filename)
        return json.loads(data) if data else None

    # pointer and status -------------------------------------------------------

    def current(self) -> dict[str, Any] | None:
        data = self.store.read(self._path("current.json"))
        return json.loads(data) if data else None

    def set_current(
        self, version: str | None, stage: str, pinned: bool = False, reason: str = ""
    ) -> dict[str, Any]:
        """Write the pointer. Call this last in a training run."""
        doc = {
            "version": version,
            "stage": stage,
            "pinned": pinned,
            "reason": reason,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.store.write(self._path("current.json"), _dumps(doc))
        return doc

    def write_status(self, status: dict[str, Any]) -> None:
        self.store.write(self._path("status.json"), _dumps(status))

    def read_status(self) -> dict[str, Any] | None:
        data = self.store.read(self._path("status.json"))
        return json.loads(data) if data else None


def _dumps(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")

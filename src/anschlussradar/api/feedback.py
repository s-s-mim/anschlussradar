"""'Hat's geklappt?': travellers confirm whether a transfer worked.

The answer is stored with the transfer it belongs to and the time it arrived, and
nothing else: no IP address, no device ID, no account. It serves two purposes:
checking the model against what people experienced, and spotting stations where
the minimum transfer time is too short or too long.

One JSON file per answer in Blob Storage (feedback/yyyy/mm/dd/<uuid>.json). Data
Explorer can read the folder as an external table when there is enough of it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

MAX_TEXT = 120
MAX_PER_HOUR = 20  # per client, the same in-memory limiter as the contact form


class FeedbackError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True, slots=True)
class TransferFeedback:
    station: str
    hub_eva: int | None  # set when the station is a recorded hub
    in_train: str
    out_train: str
    planned_arrival: str
    planned_departure: str
    made: bool
    received_at: str


def _text(body: dict[str, Any], name: str) -> str:
    value = str(body.get(name) or "").strip()
    if not value or len(value) > MAX_TEXT:
        raise FeedbackError(name, f"'{name}' must have 1 to {MAX_TEXT} characters.")
    return value


def _time(body: dict[str, Any], name: str) -> datetime:
    try:
        t = datetime.fromisoformat(str(body.get(name)))
    except ValueError:
        raise FeedbackError(name, f"'{name}' must be an ISO time with offset.") from None
    if t.tzinfo is None:
        raise FeedbackError(name, f"'{name}' must include the time zone offset.")
    return t


def validate(body: Any, now: datetime) -> dict[str, Any]:
    """Checked fields, or FeedbackError. Answers are only taken after the transfer
    and within a day, so nobody can rate a train that has not run yet."""
    if not isinstance(body, dict):
        raise FeedbackError("body", "Expected a JSON object.")
    made = body.get("made")
    if not isinstance(made, bool):
        raise FeedbackError("made", "'made' must be true or false.")
    arrival = _time(body, "plannedArrival")
    departure = _time(body, "plannedDeparture")
    if departure > now + timedelta(minutes=5) or departure < now - timedelta(hours=24):
        raise FeedbackError(
            "plannedDeparture", "Answers are taken from the departure up to a day later."
        )
    if arrival > departure:
        raise FeedbackError("plannedArrival", "The arrival must be before the departure.")
    return {
        "station": _text(body, "station"),
        "in_train": _text(body, "inTrain"),
        "out_train": _text(body, "outTrain"),
        "planned_arrival": arrival.isoformat(),
        "planned_departure": departure.isoformat(),
        "made": made,
    }


class FeedbackStore(Protocol):
    def save(self, fb: TransferFeedback) -> None: ...


class MemoryFeedbackStore:
    """For tests and local runs."""

    def __init__(self) -> None:
        self.items: list[TransferFeedback] = []

    def save(self, fb: TransferFeedback) -> None:
        self.items.append(fb)


class BlobFeedbackStore:
    def __init__(self, account_url: str, container: str = "feedback") -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self._container = service.get_container_client(container)

    def save(self, fb: TransferFeedback) -> None:
        day = fb.received_at[:10].replace("-", "/")
        name = f"{day}/{uuid.uuid4().hex}.json"
        self._container.upload_blob(name, json.dumps(asdict(fb)).encode(), overwrite=False)

"""Watched connections: "check this journey every weekday morning and warn me".

No accounts. The phone makes up a random device ID and keeps it; the server
stores per device only the push address the browser gave it, and per watched
journey the two stations, the departure time, the weekdays and the language.
Everything of a device is deleted when it switches alerts off, or 90 days after
the app was last opened.

Storage: Azure Table Storage (two tables in the Functions storage account),
accessed with the Function App's managed identity.
"""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

MAX_WATCHES_PER_DEVICE = 5
INACTIVE_DAYS = 90
_DEVICE = re.compile(r"^[0-9a-f]{32}$")
_PLACE = re.compile(r"^-?\d{1,2}(\.\d+)?,-?\d{1,3}(\.\d+)?$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
LANGS = {"de", "en", "tr", "uk", "pl", "ru", "ro", "mk", "ar", "ur", "hi", "bn", "am"}


class WatchError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass
class Watch:
    device: str
    id: str
    from_name: str
    from_place: str
    to_name: str
    to_place: str
    departure: str  # "07:42", German time
    weekdays: str  # ISO weekdays, "12345" = Monday to Friday
    lang: str
    created: str
    last_checked: str = ""  # date of the last check, "2026-11-17"

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": {"name": self.from_name, "place": self.from_place},
            "to": {"name": self.to_name, "place": self.to_place},
            "departure": self.departure,
            "weekdays": self.weekdays,
        }


@dataclass
class Device:
    id: str
    subscription: dict[str, Any]
    last_seen: str
    extra: dict[str, Any] = field(default_factory=dict)


def valid_device(value: Any) -> str:
    device = str(value or "")
    if not _DEVICE.match(device):
        raise WatchError("device", "Unknown device.")
    return device


def validate(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise WatchError("body", "Expected a JSON object.")
    device = valid_device(body.get("device"))
    sub = body.get("subscription")
    if (
        not isinstance(sub, dict)
        or not str(sub.get("endpoint", "")).startswith("https://")
        or not isinstance(sub.get("keys"), dict)
        or not {"p256dh", "auth"} <= set(sub["keys"])
    ):
        raise WatchError("subscription", "Push is not set up in this browser.")
    out: dict[str, Any] = {"device": device, "subscription": sub}
    for side in ("from", "to"):
        place = body.get(side) or {}
        name = str(place.get("name") or "").strip()
        coords = str(place.get("place") or "")
        if not name or len(name) > 120 or not _PLACE.match(coords):
            raise WatchError(side, f"'{side}' needs a name and coordinates.")
        out[f"{side}_name"], out[f"{side}_place"] = name, coords
    departure = str(body.get("departure") or "")
    if not _HHMM.match(departure):
        raise WatchError("departure", "The departure must look like 07:42.")
    weekdays = "".join(sorted(set(str(body.get("weekdays") or ""))))
    if not weekdays or not set(weekdays) <= set("1234567"):
        raise WatchError("weekdays", "Pick at least one weekday.")
    lang = str(body.get("lang") or "de")
    out.update(departure=departure, weekdays=weekdays, lang=lang if lang in LANGS else "en")
    return out


class WatchStore(Protocol):
    def save_device(self, device: Device) -> None: ...
    def get_device(self, device_id: str) -> Device | None: ...
    def touch_device(self, device_id: str, now: datetime) -> None: ...
    def delete_device(self, device_id: str) -> None: ...
    def devices(self) -> list[Device]: ...
    def save_watch(self, watch: Watch) -> None: ...
    def watches(self, device_id: str | None = None) -> list[Watch]: ...
    def delete_watch(self, device_id: str, watch_id: str) -> bool: ...


def new_watch(fields: dict[str, Any], now: datetime) -> Watch:
    return Watch(
        device=fields["device"],
        id=uuid.uuid4().hex,
        from_name=fields["from_name"],
        from_place=fields["from_place"],
        to_name=fields["to_name"],
        to_place=fields["to_place"],
        departure=fields["departure"],
        weekdays=fields["weekdays"],
        lang=fields["lang"],
        created=now.isoformat(),
    )


def inactive(device: Device, now: datetime) -> bool:
    try:
        seen = datetime.fromisoformat(device.last_seen)
    except ValueError:
        return True
    return now - seen > timedelta(days=INACTIVE_DAYS)


class MemoryWatchStore:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._watches: dict[tuple[str, str], Watch] = {}

    def save_device(self, device: Device) -> None:
        self._devices[device.id] = device

    def get_device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def touch_device(self, device_id: str, now: datetime) -> None:
        if device_id in self._devices:
            self._devices[device_id].last_seen = now.isoformat()

    def delete_device(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        for key in [k for k in self._watches if k[0] == device_id]:
            del self._watches[key]

    def devices(self) -> list[Device]:
        return list(self._devices.values())

    def save_watch(self, watch: Watch) -> None:
        self._watches[(watch.device, watch.id)] = watch

    def watches(self, device_id: str | None = None) -> list[Watch]:
        return [w for (d, _), w in self._watches.items() if device_id in (None, d)]

    def delete_watch(self, device_id: str, watch_id: str) -> bool:
        return self._watches.pop((device_id, watch_id), None) is not None


class TableWatchStore:
    """Two tables: 'devices' (PartitionKey 'device', RowKey = device ID) and
    'watches' (PartitionKey = device ID, RowKey = watch ID)."""

    def __init__(self, account_url: str) -> None:
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        service = TableServiceClient(endpoint=account_url, credential=DefaultAzureCredential())
        self._devices = service.create_table_if_not_exists("devices")
        self._watches = service.create_table_if_not_exists("watches")

    def save_device(self, device: Device) -> None:
        self._devices.upsert_entity({
            "PartitionKey": "device", "RowKey": device.id,
            "subscription": json.dumps(device.subscription), "last_seen": device.last_seen,
        })  # fmt: skip

    def get_device(self, device_id: str) -> Device | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            e = self._devices.get_entity("device", device_id)
        except ResourceNotFoundError:
            return None
        return Device(e["RowKey"], json.loads(e["subscription"]), e["last_seen"])

    def touch_device(self, device_id: str, now: datetime) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with contextlib.suppress(ResourceNotFoundError):  # unknown device: nothing to touch
            self._devices.update_entity(
                {"PartitionKey": "device", "RowKey": device_id, "last_seen": now.isoformat()},
                mode="merge",
            )

    def delete_device(self, device_id: str) -> None:
        for w in self.watches(device_id):
            self._watches.delete_entity(device_id, w.id)
        self._devices.delete_entity("device", device_id)

    def devices(self) -> list[Device]:
        return [
            Device(e["RowKey"], json.loads(e["subscription"]), e["last_seen"])
            for e in self._devices.query_entities("PartitionKey eq 'device'")
        ]

    def save_watch(self, watch: Watch) -> None:
        data = asdict(watch)
        self._watches.upsert_entity(
            {"PartitionKey": data.pop("device"), "RowKey": data.pop("id"), **data}
        )

    def watches(self, device_id: str | None = None) -> list[Watch]:
        if device_id is None:
            entities = self._watches.list_entities()
        else:
            entities = self._watches.query_entities(
                "PartitionKey eq @d", parameters={"d": device_id}
            )
        fields = Watch.__dataclass_fields__
        return [
            Watch(device=e["PartitionKey"], id=e["RowKey"],
                  **{k: e.get(k, "") for k in fields if k not in ("device", "id")})
            for e in entities
        ]  # fmt: skip

    def delete_watch(self, device_id: str, watch_id: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._watches.delete_entity(device_id, watch_id)
        except ResourceNotFoundError:
            return False
        return True


def today_departure(watch: Watch, now: datetime, tz: Any) -> datetime | None:
    """Today's departure as an aware datetime, or None if today is not a watched day."""
    local = now.astimezone(tz)
    if str(local.isoweekday()) not in watch.weekdays:
        return None
    h, m = map(int, watch.departure.split(":"))
    return local.replace(hour=h, minute=m, second=0, microsecond=0).astimezone(UTC)

"""Web Push: send a short message to a phone that switched alerts on.

VAPID keys identify this server to the push services of Apple, Google and Mozilla.
The private key lives in Key Vault; the public key is handed to the browser.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class PushGone(Exception):
    """The browser's subscription no longer exists (uninstalled, permission removed)."""


class Pusher(Protocol):
    def send(self, subscription: dict[str, Any], payload: dict[str, Any]) -> None: ...


@dataclass
class MemoryPusher:
    sent: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    gone: set[str] = field(default_factory=set)

    def send(self, subscription: dict[str, Any], payload: dict[str, Any]) -> None:
        if subscription.get("endpoint") in self.gone:
            raise PushGone(subscription["endpoint"])
        self.sent.append((subscription, payload))


class WebPusher:
    def __init__(self, private_key: str, subject: str) -> None:
        self.private_key = private_key
        self.subject = subject  # https URL or mailto: identifying the sender

    def send(self, subscription: dict[str, Any], payload: dict[str, Any]) -> None:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject},
                ttl=3600,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                raise PushGone(subscription.get("endpoint", "")) from exc
            raise

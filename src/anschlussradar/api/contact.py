"""Contact form: validation, spam guards, rate limit, e-mail to the owner.

Messages are not stored by the app. They are sent to the owner's inbox through
Azure Communication Services, with the sender's address as Reply-To. No message is
ever sent to the address someone types in, so the form cannot be abused to send
e-mail to strangers.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Protocol

TOPICS = ("question", "feedback", "problem", "privacy", "other")
TOPIC_LABELS = {
    "question": "Question",
    "feedback": "Feedback",
    "problem": "Report a problem",
    "privacy": "Data or privacy",
    "other": "Other",
}
_EMAIL = re.compile(r"^[^@\s<>\"]+@[^@\s<>\"]+\.[A-Za-z]{2,}$")
MIN_SECONDS_ON_PAGE = 3
MAX_PER_HOUR = 3


class ContactError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True, slots=True)
class ContactMessage:
    name: str
    topic: str
    email: str
    message: str


def validate(body: dict[str, Any], now: float) -> ContactMessage | None:
    """Return the message, or None for a likely bot (dropped silently).

    body: name, topic, email, message, plus two spam guards from the form:
      website    a hidden field people never fill (honeypot)
      openedAt   when the form was shown, in epoch milliseconds
    """
    if str(body.get("website") or "").strip():
        return None
    opened_at = body.get("openedAt")
    try:
        if opened_at is None or now - float(opened_at) / 1000 < MIN_SECONDS_ON_PAGE:
            return None
    except (TypeError, ValueError):
        return None

    name = " ".join(str(body.get("name") or "").split())
    topic = str(body.get("topic") or "")
    email = str(body.get("email") or "").strip()
    message = str(body.get("message") or "").strip()
    if not 2 <= len(name) <= 80:
        raise ContactError("name", "Name must be 2 to 80 characters.")
    if topic not in TOPICS:
        raise ContactError("topic", "Please choose a topic.")
    if len(email) > 254 or not _EMAIL.match(email):
        raise ContactError("email", "Please enter a valid e-mail address.")
    if not 10 <= len(message) <= 3000:
        raise ContactError("message", "Message must be 10 to 3,000 characters.")
    return ContactMessage(name, topic, email, message)


class RateLimiter:
    """At most `limit` messages per hour per sender, kept in memory per instance.

    The client address is hashed, so no IP address is held in plain text.
    """

    def __init__(self, limit: int = MAX_PER_HOUR, window_s: float = 3600.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        key = hashlib.sha256(client.encode()).hexdigest()[:16]
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


class EmailSender(Protocol):
    def send(self, msg: ContactMessage) -> None: ...


def compose(msg: ContactMessage) -> tuple[str, str]:
    subject = f"[AnschlussRadar] {TOPIC_LABELS[msg.topic]} from {msg.name}"
    body = f"Name: {msg.name}\nE-mail: {msg.email}\nTopic: {TOPIC_LABELS[msg.topic]}\n\n{msg.message}\n"
    return subject, body


class AcsEmailSender:
    """Azure Communication Services Email, with a connection string or Entra ID."""

    def __init__(
        self, sender: str, recipient: str, endpoint: str = "", connection_string: str = ""
    ) -> None:
        from azure.communication.email import EmailClient

        if connection_string:
            self._client = EmailClient.from_connection_string(connection_string)
        else:
            from azure.identity import DefaultAzureCredential

            self._client = EmailClient(endpoint, DefaultAzureCredential())
        self.sender, self.recipient = sender, recipient

    def send(self, msg: ContactMessage) -> None:
        subject, body = compose(msg)
        poller = self._client.begin_send(
            {
                "senderAddress": self.sender,
                "recipients": {"to": [{"address": self.recipient}]},
                "replyTo": [{"address": msg.email, "displayName": msg.name}],
                "content": {"subject": subject, "plainText": body},
            }
        )
        poller.result()

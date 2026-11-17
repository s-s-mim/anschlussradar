"""The question box: questions the help texts could not answer.

A question is stored without name or e-mail. The phone keeps the random question
ID and asks for the answer later ("Meine Fragen"). If the person ticked "notify
me", the phone's push address is stored with the question and the 10-minute
timer sends the answer once it exists.

Answers are written by the operator with scripts/questions.py. The AI step
(assistant.py) never answers saved questions, also not after it is switched on:
it only answers questions asked while it is on. Answered questions are deleted 30 days
after the answer, unanswered ones after 60 days.
"""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from .watch import LANGS

MIN_LEN, MAX_LEN = 5, 500
# Test phase: small limits on purpose. The web app shows QUESTIONS_PER_DAY to the user.
QUESTIONS_PER_DAY = 2  # per person (address), rolling 24 hours
QUESTIONS_DAILY_TOTAL = 50  # for the whole app
KEEP_ANSWERED = timedelta(days=30)
KEEP_OPEN = timedelta(days=60)
_ID = re.compile(r"^[0-9a-f]{32}$")


class QuestionError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass
class Question:
    id: str
    text: str
    lang: str
    created: str
    subscription: str = ""  # JSON push subscription, only if the person asked to be notified
    answer: str = ""
    answered_at: str = ""
    answered_by: str = ""  # "operator" or "assistant"
    notified: str = ""  # "1" once the push went out

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "answer": self.answer or None,
            "answeredAt": self.answered_at or None,
        }


def valid_id(value: Any) -> str:
    s = str(value or "")
    if not _ID.match(s):
        raise QuestionError("id", "Unknown question.")
    return s


def validate(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise QuestionError("body", "Expected a JSON object.")
    text = " ".join(str(body.get("text") or "").split())
    if not MIN_LEN <= len(text) <= MAX_LEN:
        raise QuestionError("text", f"The question needs {MIN_LEN} to {MAX_LEN} characters.")
    lang = str(body.get("lang") or "de")
    sub = body.get("subscription")
    if sub is not None and (
        not isinstance(sub, dict)
        or not str(sub.get("endpoint", "")).startswith("https://")
        or not isinstance(sub.get("keys"), dict)
        or not {"p256dh", "auth"} <= set(sub["keys"])
    ):
        raise QuestionError("subscription", "Push is not set up in this browser.")
    return {
        "text": text,
        "lang": lang if lang in LANGS else "en",
        "subscription": json.dumps(sub) if sub else "",
    }


def new_question(fields: dict[str, Any], now: datetime) -> Question:
    return Question(id=uuid.uuid4().hex, created=now.isoformat(), **fields)


def expired(q: Question, now: datetime) -> bool:
    if q.answered_at:
        return now - datetime.fromisoformat(q.answered_at) > KEEP_ANSWERED
    return now - datetime.fromisoformat(q.created) > KEEP_OPEN


class QuestionStore(Protocol):
    def save(self, q: Question) -> None: ...
    def get(self, qid: str) -> Question | None: ...
    def all(self) -> list[Question]: ...
    def delete(self, qid: str) -> None: ...


class MemoryQuestionStore:
    def __init__(self) -> None:
        self.items: dict[str, Question] = {}

    def save(self, q: Question) -> None:
        self.items[q.id] = Question(**asdict(q))

    def get(self, qid: str) -> Question | None:
        q = self.items.get(qid)
        return Question(**asdict(q)) if q else None

    def all(self) -> list[Question]:
        return [Question(**asdict(q)) for q in self.items.values()]

    def delete(self, qid: str) -> None:
        self.items.pop(qid, None)


class TableQuestionStore:
    """Table 'questions' (PartitionKey 'q', RowKey = question ID), in the same
    storage account as the watched connections."""

    def __init__(self, account_url: str, credential: Any = None) -> None:
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        service = TableServiceClient(
            endpoint=account_url, credential=credential or DefaultAzureCredential()
        )
        self._table = service.create_table_if_not_exists("questions")

    def save(self, q: Question) -> None:
        row = asdict(q)
        qid = row.pop("id")
        self._table.upsert_entity({"PartitionKey": "q", "RowKey": qid, **row})

    def _from(self, e: dict[str, Any]) -> Question:
        fields = Question.__dataclass_fields__
        return Question(id=e["RowKey"], **{k: e.get(k, "") for k in fields if k != "id"})

    def get(self, qid: str) -> Question | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._from(self._table.get_entity("q", qid))
        except ResourceNotFoundError:
            return None

    def all(self) -> list[Question]:
        return [self._from(e) for e in self._table.query_entities("PartitionKey eq 'q'")]

    def delete(self, qid: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with contextlib.suppress(ResourceNotFoundError):  # already gone
            self._table.delete_entity("q", qid)


NOTIFY_TEXTS = {
    "de": ("Deine Frage wurde beantwortet", "Tippe hier, um die Antwort zu lesen."),
    "en": ("Your question has an answer", "Tap here to read it."),
    "tr": ("Sorun yanıtlandı", "Yanıtı okumak için dokun."),
    "uk": ("На ваше запитання відповіли", "Торкніться, щоб прочитати відповідь."),
    "pl": ("Twoje pytanie ma odpowiedź", "Dotknij, aby ją przeczytać."),
    "ru": ("На ваш вопрос ответили", "Нажмите, чтобы прочитать ответ."),
    "ro": ("Întrebarea ta are un răspuns", "Atinge pentru a-l citi."),
    "mk": ("Вашето прашање има одговор", "Допрете за да го прочитате."),
    "ar": ("تمت الإجابة عن سؤالك", "اضغط هنا لقراءة الإجابة."),
    "ur": ("آپ کے سوال کا جواب آ گیا ہے", "جواب پڑھنے کے لیے یہاں چھوئیں۔"),
    "hi": ("आपके सवाल का जवाब आ गया है", "जवाब पढ़ने के लिए यहाँ टैप करें।"),
    "bn": ("আপনার প্রশ্নের উত্তর এসেছে", "উত্তর পড়তে এখানে চাপুন।"),
    "am": ("ለጥያቄዎ መልስ ተሰጥቷል", "መልሱን ለማንበብ እዚህ ይንኩ።"),
}


def notify_payload(q: Question) -> dict[str, str]:
    title, body = NOTIFY_TEXTS.get(q.lang, NOTIFY_TEXTS["en"])
    return {"title": title, "body": body, "url": f"/help?question={q.id}#my-questions"}

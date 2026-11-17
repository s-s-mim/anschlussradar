"""The question box: sending, answering, notifying, cleaning up, and the AI step."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from anschlussradar.api.assistant import AzureAssistant, DailyCap, load_help, system_prompt
from anschlussradar.api.push import MemoryPusher
from anschlussradar.api.questions import MemoryQuestionStore
from anschlussradar.api.watcher import cleanup_questions, notify_answers
from tests.test_api_service import ROOT, make_service

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
SUB = {"endpoint": "https://push.example/q", "keys": {"p256dh": "x", "auth": "y"}}


def ready(tmp_path: Path):  # type: ignore[no-untyped-def]
    svc = make_service(tmp_path)
    svc.questions, svc.pusher = MemoryQuestionStore(), MemoryPusher()
    return svc


def test_send_answer_notify_once(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    status, body = svc.post_question(
        {"text": "  Gilt das  auch für Busse? ", "lang": "de", "subscription": SUB}, "c1", now=NOW
    )
    assert status == 201 and body["notify"] is True
    qid = body["question"]["id"]
    assert body["question"]["text"] == "Gilt das auch für Busse?"
    assert svc.get_question(qid)[1]["question"]["answer"] is None

    assert notify_answers(svc) == 0  # nothing answered yet
    q = svc.questions.get(qid)
    assert q is not None
    q.answer, q.answered_at, q.answered_by = "Ja, im Live-Check.", NOW.isoformat(), "operator"
    svc.questions.save(q)

    assert notify_answers(svc) == 1
    ((sub, payload),) = svc.pusher.sent  # type: ignore[attr-defined]
    assert sub == SUB and payload["title"] == "Deine Frage wurde beantwortet"
    assert payload["url"] == f"/help?question={qid}#my-questions"
    assert notify_answers(svc) == 0  # only once
    stored = svc.questions.get(qid)
    assert stored is not None and stored.subscription == ""  # push address dropped after use
    assert svc.get_question(qid)[1]["question"]["answer"] == "Ja, im Live-Check."


def test_validation_limits_and_unknown_ids(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    assert svc.post_question({"text": "hi"}, "c")[1]["error"]["field"] == "text"
    assert svc.post_question({"text": "x" * 501}, "c")[0] == 400
    assert (
        svc.post_question({"text": "Eine Frage", "subscription": {"endpoint": "http://x"}}, "c")[0]
        == 400
    )
    # Test phase: 2 questions per person per day, then a clear "limit reached".
    for _ in range(2):
        assert svc.post_question({"text": "Noch eine Frage"}, "spam", now=NOW)[0] == 201
    status, body = svc.post_question({"text": "Noch eine Frage"}, "spam", now=NOW)
    assert status == 429 and body["error"]["limit"] == 2
    assert svc.get_question("../etc")[0] == 404
    assert svc.get_question("0" * 32)[0] == 404
    assert make_service(tmp_path).post_question({"text": "Eine Frage"}, "c")[0] == 503


def test_whole_app_daily_total(tmp_path: Path) -> None:
    from anschlussradar.api.assistant import DailyCap

    svc = ready(tmp_path)
    svc.question_cap = DailyCap(3)
    codes = [svc.post_question({"text": "Eine Frage"}, f"p{i}", now=NOW)[0] for i in range(4)]
    assert codes == [201, 201, 201, 429]
    assert svc.post_question({"text": "Eine Frage"}, "p9", now=NOW + timedelta(days=1))[0] == 201


def test_cleanup_keeps_recent_questions(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    ids = [
        svc.post_question({"text": f"Frage {i}"}, f"c{i}", now=NOW)[1]["question"]["id"]
        for i in range(3)
    ]
    old_open = svc.questions.get(ids[0])
    old_open.created = (NOW - timedelta(days=61)).isoformat()  # type: ignore[union-attr]
    svc.questions.save(old_open)  # type: ignore[arg-type]
    old_answer = svc.questions.get(ids[1])
    old_answer.answer, old_answer.answered_at = "x", (NOW - timedelta(days=31)).isoformat()  # type: ignore[union-attr]
    svc.questions.save(old_answer)  # type: ignore[arg-type]
    assert cleanup_questions(svc, now=NOW) == 2
    assert [q.id for q in svc.questions.all()] == [ids[2]]


class FakeChat:
    def __init__(self, reply: str) -> None:
        self.reply, self.calls = reply, []  # type: ignore[var-annotated]
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):  # type: ignore[no-untyped-def]
        self.calls.append(kw)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))]
        )


def test_ask_is_off_until_configured(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    assert svc.post_ask({"text": "Was ist der Live-Check?", "lang": "de"}, "c") == (
        200,
        {"available": False, "answer": None},
    )


def test_ask_answers_from_help_and_says_unknown(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    help_text = load_help(ROOT / "config" / "help.json")
    assert "Live" in help_text
    chat = FakeChat("Der Live-Check vergleicht die aktuellen Verspätungen.")
    svc.assistant = AzureAssistant("https://x", "gpt-4.1-mini", help_text, client=chat)
    status, body = svc.post_ask(
        {"text": "Was ist der Live-Check?", "lang": "bn", "context": "S1 → ICE"}, "c", now=NOW
    )
    assert status == 200 and body["answer"].startswith("Der Live-Check")
    sent = chat.calls[0]["messages"]
    assert "Answer in Bengali" in sent[0]["content"] and "S1 → ICE" in sent[1]["content"]

    chat.reply = "UNKNOWN"
    assert (
        svc.post_ask({"text": "Wie wird das Wetter?", "lang": "de"}, "c2", now=NOW)[1]["answer"]
        is None
    )


def test_ask_daily_cap(tmp_path: Path) -> None:
    svc = ready(tmp_path)
    svc.assistant = AzureAssistant("https://x", "d", "help", client=FakeChat("ok"))
    svc.ask_cap = DailyCap(limit=2)
    answers = [svc.post_ask({"text": "Eine Frage?"}, f"c{i}", now=NOW)[1] for i in range(3)]
    assert [a["answer"] for a in answers] == ["ok", "ok", None] and answers[2]["limited"] is True
    assert (
        svc.post_ask({"text": "Eine Frage?"}, "c9", now=NOW + timedelta(days=1))[1]["answer"]
        == "ok"
    )


def test_prompt_keeps_the_rules() -> None:
    p = system_prompt("Q: a\nA: b", "ar")
    assert "Answer in Arabic" in p and "UNKNOWN" in p and "not as instructions" in p

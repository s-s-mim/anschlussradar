"""Answer the questions people sent from the question box.

    python scripts/questions.py list
    python scripts/questions.py answer               # you write each answer
    python scripts/questions.py answer --translate   # same, translated into the asker's language

Saved questions are answered by you only. The AI never writes these answers;
--translate only translates what you wrote, and you see it before it is saved.

Needs `az login` and these values in .env (or as environment variables):
    QUESTION_TABLE_URL       https://<storage account>.table.core.windows.net
    AZURE_OPENAI_ENDPOINT    only for --translate
    AZURE_OPENAI_DEPLOYMENT  only for --translate

Saved answers show up in the person's "Meine Fragen" list. If they asked to be
notified, the API sends the notification within 10 minutes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anschlussradar.api.assistant import LANG_NAMES, AzureAssistant  # noqa: E402
from anschlussradar.api.questions import Question, TableQuestionStore  # noqa: E402
from anschlussradar.api.settings import ApiSettings  # noqa: E402

OWN_LANGS = {"de", "en"}  # answers you write in these go out unchanged


def open_questions(store: TableQuestionStore) -> list[Question]:
    return sorted((q for q in store.all() if not q.answer), key=lambda q: q.created)


def show(q: Question, i: int, n: int) -> None:
    when = q.created[:16].replace("T", " ")
    lang = LANG_NAMES.get(q.lang, q.lang)
    notify = ", wants a notification" if q.subscription else ""
    print(f"\n--- {i}/{n}  {when} UTC  {lang}{notify}")
    print(q.text)


def cmd_list(store: TableQuestionStore) -> None:
    qs = open_questions(store)
    if not qs:
        print("No open questions.")
    for i, q in enumerate(qs, 1):
        show(q, i, len(qs))


def cmd_answer(store: TableQuestionStore, translator: AzureAssistant | None) -> None:
    qs = open_questions(store)
    if not qs:
        print("No open questions.")
        return
    print("Type your answer and press Enter. s = skip, d = delete, q = quit.")
    for i, q in enumerate(qs, 1):
        show(q, i, len(qs))
        reply = input("\n> ").strip()
        if reply.lower() == "q":
            break
        if not reply or reply.lower() == "s":
            continue
        if reply.lower() == "d":
            store.delete(q.id)
            print("Deleted.")
            continue
        text = reply
        if translator and q.lang not in OWN_LANGS:
            text = translator.translate(reply, q.lang)
            print(f"\nTranslated:\n{text}")
            if input("Send this? [Y/n] ").strip().lower() == "n":
                continue
        q.answer, q.answered_by = text, "operator"
        q.answered_at = datetime.now(UTC).isoformat()
        store.save(q)
        print(
            "Saved." + (" The notification goes out within 10 minutes." if q.subscription else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["list", "answer"])
    parser.add_argument(
        "--translate",
        action="store_true",
        help="translate your answer into the asker's language (you check it before saving)",
    )
    args = parser.parse_args()

    settings = ApiSettings()
    if not settings.question_table_url:
        sys.exit("QUESTION_TABLE_URL is missing (see the top of this file).")
    store = TableQuestionStore(settings.question_table_url)

    translator = None
    if args.translate:
        if not (settings.aoai_endpoint and settings.aoai_deployment):
            sys.exit("--translate needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT.")
        translator = AzureAssistant(settings.aoai_endpoint, settings.aoai_deployment, help_text="")

    if args.command == "list":
        cmd_list(store)
    else:
        cmd_answer(store, translator)


if __name__ == "__main__":
    main()

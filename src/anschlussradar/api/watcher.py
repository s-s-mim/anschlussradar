"""The morning check: about an hour before a watched train leaves, look at the
live situation and send a push only when a transfer is at risk.

Runs every 10 minutes (timer in the API Function App). One journey search per
watched connection and day, so the load on Transitous stays tiny.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .journeys import Journey, build_journeys
from .push import PushGone
from .questions import expired, notify_payload
from .transitous import TransitousError
from .watch import Watch, inactive, today_departure

if TYPE_CHECKING:
    from .service import ApiService

log = logging.getLogger(__name__)
BERLIN = ZoneInfo("Europe/Berlin")
WINDOW = (45, 75)  # minutes before departure

# Push texts, in the language the phone used when the watch was made.
TEXTS: dict[str, tuple[str, str, str]] = {
    "de": ("Der Umstieg in {station} klappt heute wohl nicht.", "Der Umstieg in {station} ist heute gefährdet.", "Ein Zug deiner Verbindung fällt heute aus."),
    "en": ("The change at {station} probably won't work today.", "The change at {station} is at risk today.", "A train on your journey is cancelled today."),
    "tr": ("{station} aktarması bugün muhtemelen yetişmeyecek.", "{station} aktarması bugün risk altında.", "Bağlantınızdaki bir tren bugün iptal."),
    "uk": ("Пересадка в {station} сьогодні, імовірно, не вдасться.", "Пересадка в {station} сьогодні під загрозою.", "Один із потягів вашого маршруту сьогодні скасовано."),
    "pl": ("Przesiadka w {station} dziś raczej się nie uda.", "Przesiadka w {station} jest dziś zagrożona.", "Jeden z pociągów twojego połączenia jest dziś odwołany."),
    "ru": ("Пересадка в {station} сегодня, скорее всего, не удастся.", "Пересадка в {station} сегодня под угрозой.", "Один из поездов вашего маршрута сегодня отменён."),
    "ro": ("Transferul din {station} probabil nu reușește azi.", "Transferul din {station} este azi în pericol.", "Un tren din legătura ta este anulat azi."),
    "mk": ("Преседнувањето во {station} денес веројатно нема да успее.", "Преседнувањето во {station} денес е загрозено.", "Еден воз од вашата врска денес е откажан."),
    "ar": ("التبديل في {station} لن ينجح اليوم على الأرجح.", "التبديل في {station} معرّض للخطر اليوم.", "أحد قطارات رحلتك ملغى اليوم."),
    "ur": ("{station} پر ٹرین بدلنا آج شاید نہیں ہو پائے گا۔", "{station} پر ٹرین بدلنا آج خطرے میں ہے۔", "آپ کے سفر کی ایک ٹرین آج منسوخ ہے۔"),
    "hi": ("{station} पर ट्रेन बदलना आज शायद नहीं हो पाएगा।", "{station} पर ट्रेन बदलना आज ख़तरे में है।", "आपकी यात्रा की एक ट्रेन आज रद्द है।"),
    "bn": ("{station}-এ আজ ট্রেন বদল সম্ভবত হবে না।", "{station}-এ আজ ট্রেন বদল ঝুঁকিতে আছে।", "আপনার যাত্রার একটি ট্রেন আজ বাতিল।"),
    "am": ("በ{station} ዛሬ ባቡር መቀየሩ ምናልባት አይሳካም።", "በ{station} ዛሬ ባቡር መቀየሩ አደጋ ላይ ነው።", "የጉዞዎ አንድ ባቡር ዛሬ ተሰርዟል።"),
}  # fmt: skip


@dataclass
class CheckResult:
    checked: int = 0
    alerts: int = 0
    not_found: int = 0
    errors: int = 0


def problem(journey: Journey) -> tuple[str, str | None] | None:
    """('missed'|'risk'|'cancelled', station) for the worst problem, or None if all is fine."""
    if any(leg.cancelled for leg in journey.legs if leg.transit):
        return "cancelled", None
    worst: tuple[str, str | None] | None = None
    for t in journey.transfers:
        if t.live_status in ("missed", "cancelled"):
            return "missed", t.station
        if t.live_status == "at_risk" and worst is None:
            worst = ("risk", t.station)
    return worst


def message(watch: Watch, kind: str, station: str | None) -> dict[str, str]:
    missed, risk, cancelled = TEXTS.get(watch.lang, TEXTS["en"])
    text = {"missed": missed, "risk": risk, "cancelled": cancelled}[kind]
    url = "/connections?" + urlencode({
        "from": watch.from_place, "fromName": watch.from_name,
        "to": watch.to_place, "toName": watch.to_name,
        "date": datetime.now(BERLIN).date().isoformat(), "time": watch.departure,
    })  # fmt: skip
    if watch.local == "1":
        url += "&local=1"
    return {
        "title": f"{watch.departure} {watch.from_name} → {watch.to_name}",
        "body": text.format(station=station or ""),
        "url": url,
    }


def find_journey(journeys: list[Journey], departure: datetime) -> Journey | None:
    for j in journeys:
        first = next((leg for leg in j.legs if leg.transit), None)
        if (
            first
            and first.dep_planned
            and abs((first.dep_planned - departure).total_seconds()) <= 60
        ):
            return j
    return None


def check_watches(svc: ApiService, now: datetime | None = None) -> CheckResult:
    result = CheckResult()
    if svc.watches is None or svc.pusher is None:
        return result
    now = now or datetime.now(UTC)
    today = now.astimezone(BERLIN).date().isoformat()
    model = svc.models.get()
    for watch in svc.watches.watches():
        dep = today_departure(watch, now, BERLIN)
        if dep is None or watch.last_checked == today:
            continue
        minutes = (dep - now).total_seconds() / 60
        if not WINDOW[0] <= minutes <= WINDOW[1]:
            continue
        result.checked += 1
        watch.last_checked = today
        svc.watches.save_watch(watch)
        try:
            plan = svc.transitous.plan(
                watch.from_place,
                watch.to_place,
                dep - timedelta(minutes=1),
                rail_only=watch.local != "1",
                num_itineraries=3,
            )
        except TransitousError:
            result.errors += 1
            continue
        journeys = build_journeys(plan, model, svc.hubs, svc.history, now, svc.messages)
        journey = find_journey(journeys, dep)
        if journey is None:
            result.not_found += 1
            continue
        found = problem(journey)
        if found is None:
            continue  # all fine: stay quiet
        device = svc.watches.get_device(watch.device)
        if device is None:
            continue
        try:
            svc.pusher.send(device.subscription, message(watch, *found))
            result.alerts += 1
        except PushGone:
            svc.watches.delete_device(watch.device)
        except Exception:
            log.exception("push failed")
            result.errors += 1
    return result


def cleanup(svc: ApiService, now: datetime | None = None) -> int:
    """Delete devices (and their watches) not seen for 90 days."""
    if svc.watches is None:
        return 0
    now = now or datetime.now(UTC)
    gone = [d.id for d in svc.watches.devices() if inactive(d, now)]
    for device_id in gone:
        svc.watches.delete_device(device_id)
    return len(gone)


def notify_answers(svc: ApiService) -> int:
    """Push 'your question has an answer' to phones that asked for it."""
    if svc.questions is None or svc.pusher is None:
        return 0
    sent = 0
    for q in svc.questions.all():
        if not q.answer or not q.subscription or q.notified:
            continue
        try:
            svc.pusher.send(json.loads(q.subscription), notify_payload(q))
            sent += 1
        except PushGone:
            pass  # the phone switched notifications off; the answer stays in "Meine Fragen"
        except Exception:
            log.exception("could not send an answer notification")
            continue
        # Notified (or no longer reachable): the push address is not needed any more.
        q.notified, q.subscription = "1", ""
        svc.questions.save(q)
    return sent


def cleanup_questions(svc: ApiService, now: datetime | None = None) -> int:
    """Delete questions 30 days after the answer, or after 60 days without one."""
    if svc.questions is None:
        return 0
    now = now or datetime.now(UTC)
    old = [q.id for q in svc.questions.all() if expired(q, now)]
    for qid in old:
        svc.questions.delete(qid)
    return len(old)

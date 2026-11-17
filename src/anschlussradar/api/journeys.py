"""Turn Transitous itineraries into journeys with a reliability score per transfer.

For each change between two trains:
  * the model's probability that the transfer works (stage early or full), using
    history counts when the station is a recorded hub
  * on the day of travel, a live check from the current forecast delays
A journey's reliability is the product of its transfer probabilities. That treats the
transfers as independent; in reality one delay often spreads to the next train, so
the app presents the number as an estimate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..ml.features import (
    BERLIN,
    CATEGORY_GROUPS,
    HistoryCounts,
    TransferInput,
    buffer_bucket,
    category_group,
)
from ..ml.serving import LoadedModel, live_check, score_transfer
from ..ml.stages import Stage
from .forecast import DelayForecast, ForecastProvider
from .messages import MessageProvider, TrainMessage
from .stations import HubMatcher

NON_TRANSIT_MODES = {
    "WALK", "BIKE", "RENTAL", "CAR", "CAR_PARKING", "CAR_DROPOFF", "ODM", "RIDE_SHARING", "FLEX",
}  # fmt: skip
# When the train label has no category we know, fall back to the mode.
MODE_CATEGORY = {
    "HIGHSPEED_RAIL": "ICE",
    "LONG_DISTANCE": "IC",
    "NIGHT_RAIL": "NJ",
    "REGIONAL_FAST_RAIL": "RE",
    "REGIONAL_RAIL": "RB",
    "RAIL": "RB",
    "SUBURBAN": "S",
}
# Minimum transfer time when a bus, tram or underground line is involved. The
# planner already counts the walk between stops in the planned buffer.
LOCAL_MIN_TRANSFER = 2
_KNOWN = {c for cats in CATEGORY_GROUPS.values() for c in cats}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def minutes(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60)


def train_label(leg: dict[str, Any]) -> tuple[str | None, str | None]:
    """(category, number) from the display name, e.g. 'ICE 579' -> ('ICE', '579')."""
    category = number = None
    for text in (leg.get("displayName"), leg.get("routeShortName")):
        m = re.match(r"^\s*([A-Za-z]+)\s*(\d+)?", text or "")
        if m and m.group(1).upper() in _KNOWN:
            category, number = m.group(1).upper(), m.group(2)
            break
    if category is None:
        category = MODE_CATEGORY.get(leg.get("mode", ""))
    trip_short = leg.get("tripShortName")
    if trip_short and str(trip_short).strip().isdigit():
        number = str(trip_short).strip()
    return category, number


@dataclass
class Leg:
    mode: str
    transit: bool
    category: str | None
    number: str | None
    line: str | None
    headsign: str | None
    from_name: str
    to_name: str
    dep_planned: datetime | None
    dep_actual: datetime | None
    arr_planned: datetime | None
    arr_actual: datetime | None
    dep_track: str | None
    arr_track: str | None
    dep_track_planned: str | None
    arr_track_planned: str | None
    real_time: bool
    cancelled: bool
    messages: list[TrainMessage] = field(default_factory=list)
    from_hub: int | None = None  # station group EVA when the stop is a recorded hub
    to_hub: int | None = None
    forecast: DelayForecast | None = None  # typical departure delay at a recorded hub

    @classmethod
    def from_motis(cls, leg: dict[str, Any]) -> Leg:
        mode = leg.get("mode", "OTHER")
        frm, to = leg.get("from", {}), leg.get("to", {})
        category, number = train_label(leg)
        return cls(
            mode=mode,
            transit=mode not in NON_TRANSIT_MODES,
            category=category,
            number=number,
            # The route's short name is the line people know ("S1", "RE30"); the display
            # name can be the trip ("RE 026719") for regional trains.
            line=leg.get("routeShortName") or leg.get("displayName"),
            headsign=leg.get("headsign"),
            from_name=frm.get("name", ""),
            to_name=to.get("name", ""),
            dep_planned=parse_time(leg.get("scheduledStartTime")),
            dep_actual=parse_time(leg.get("startTime")),
            arr_planned=parse_time(leg.get("scheduledEndTime")),
            arr_actual=parse_time(leg.get("endTime")),
            dep_track=frm.get("track"),
            arr_track=to.get("track"),
            dep_track_planned=frm.get("scheduledTrack"),
            arr_track_planned=to.get("scheduledTrack"),
            real_time=bool(leg.get("realTime")),
            cancelled=bool(leg.get("cancelled") or frm.get("cancelled") or to.get("cancelled")),
        )

    @property
    def dep_delay(self) -> int | None:
        return minutes(self.dep_planned, self.dep_actual) if self.real_time else None

    @property
    def arr_delay(self) -> int | None:
        return minutes(self.arr_planned, self.arr_actual) if self.real_time else None

    @property
    def is_rail(self) -> bool:
        return self.transit and category_group(self.category) != "other"

    def to_dict(self) -> dict[str, Any]:
        def iso(t: datetime | None) -> str | None:
            return t.astimezone(BERLIN).isoformat() if t else None

        return {
            "mode": self.mode,
            "line": self.line,
            "category": self.category,
            "number": self.number,
            "headsign": self.headsign,
            "from": self.from_name,
            "to": self.to_name,
            "departurePlanned": iso(self.dep_planned),
            "departure": iso(self.dep_actual),
            "arrivalPlanned": iso(self.arr_planned),
            "arrival": iso(self.arr_actual),
            "departureDelay": self.dep_delay,
            "arrivalDelay": self.arr_delay,
            "departureTrack": self.dep_track,
            "departureTrackPlanned": self.dep_track_planned,
            "arrivalTrack": self.arr_track,
            "arrivalTrackPlanned": self.arr_track_planned,
            "realTime": self.real_time,
            "cancelled": self.cancelled,
            "messages": [m.to_dict() for m in self.messages],
            "fromHub": self.from_hub,
            "toHub": self.to_hub,
            "forecast": self.forecast.to_dict() if self.forecast else None,
        }


class HistoryProvider(Protocol):
    def counts(
        self, group_eva: int | None, in_number: str | None, out_number: str | None,
        in_group: str, out_group: str, bucket: str,
    ) -> HistoryCounts: ...  # fmt: skip


class NoHistory:
    def counts(self, *args: Any, **kwargs: Any) -> HistoryCounts:
        return HistoryCounts()


@dataclass
class Transfer:
    station: str
    arriving: Leg
    departing: Leg
    hub_eva: int | None
    planned_buffer: int | None
    probability: float | None = None
    confidence: str | None = None
    observations: int = 0
    early_estimate: bool = False
    live_status: str | None = None
    live_slack: int | None = None
    note: str | None = None  # a code the web app translates: cancelled, not_rail

    def to_dict(self) -> dict[str, Any]:
        return {
            "station": self.station,
            "plannedBufferMinutes": self.planned_buffer,
            "arrivalTrack": self.arriving.arr_track,
            "departureTrack": self.departing.dep_track,
            "probability": self.probability,
            "confidence": self.confidence,
            "observations": self.observations,
            "earlyEstimate": self.early_estimate,
            "liveStatus": self.live_status,
            "liveSlackMinutes": self.live_slack,
            "recordedHub": self.hub_eva is not None,
            "note": self.note,
        }


@dataclass
class Journey:
    departure: datetime | None
    arrival: datetime | None
    duration_min: int
    legs: list[Leg]
    transfers: list[Transfer] = field(default_factory=list)
    tips: list[dict[str, Any]] = field(default_factory=list)

    @property
    def scored_transfers(self) -> list[Transfer]:
        """Transfers that can get a score: train to train."""
        return [t for t in self.transfers if t.note != "not_rail"]

    @property
    def partial(self) -> bool:
        """True when some transfers involve a bus, tram or underground line."""
        return len(self.scored_transfers) < len(self.transfers)

    @property
    def reliability(self) -> float | None:
        if not self.transfers:
            return 1.0  # direct train: nothing to miss
        scored = self.scored_transfers
        if not scored:
            return None  # only local transport transfers: live check only
        probs = [t.probability for t in scored]
        if any(p is None for p in probs):
            return None
        result = 1.0
        for p in probs:
            result *= p  # type: ignore[operator]
        return round(result, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "departure": self.departure.astimezone(BERLIN).isoformat() if self.departure else None,
            "arrival": self.arrival.astimezone(BERLIN).isoformat() if self.arrival else None,
            "durationMinutes": self.duration_min,
            "transfersCount": len(self.transfers),
            "reliability": self.reliability,
            "reliabilityTrainsOnly": self.partial,
            "legs": [leg.to_dict() for leg in self.legs if leg.transit],
            "transfers": [t.to_dict() for t in self.transfers],
            "tips": self.tips,
        }


def build_journeys(
    plan: dict[str, Any],
    model: LoadedModel,
    hubs: HubMatcher,
    history: HistoryProvider,
    today: datetime,
    messages: MessageProvider | None = None,
    forecasts: ForecastProvider | None = None,
) -> list[Journey]:
    out: list[Journey] = []
    for it in [*plan.get("direct", []), *plan.get("itineraries", [])]:
        legs = [Leg.from_motis(leg) for leg in it.get("legs", [])]
        transit = [leg for leg in legs if leg.transit]
        if not transit:
            continue  # walking only
        journey = Journey(
            departure=parse_time(it.get("startTime")),
            arrival=parse_time(it.get("endTime")),
            duration_min=round(int(it.get("duration", 0)) / 60),
            legs=legs,
        )
        for arriving, departing in zip(transit, transit[1:], strict=False):
            journey.transfers.append(_score(arriving, departing, model, hubs, history, today))
        for leg in transit:
            from_hub, to_hub = hubs.match(leg.from_name), hubs.match(leg.to_name)
            leg.from_hub = from_hub.group_eva if from_hub else None
            leg.to_hub = to_hub.group_eva if to_hub else None
            if messages is not None:
                leg.messages = _leg_messages(leg, hubs, messages)
            if forecasts is not None and from_hub is not None and leg.dep_planned is not None:
                leg.forecast = forecasts.forecast(
                    from_hub.eva, leg.number, leg.category, leg.dep_planned
                )
        out.append(journey)
    return out


def _leg_messages(leg: Leg, hubs: HubMatcher, messages: MessageProvider) -> list[TrainMessage]:
    """Reasons and notes for this train at the recorded hubs where it starts or ends."""
    if not leg.number:
        return []
    found: dict[tuple[int, str], TrainMessage] = {}
    for name in (leg.from_name, leg.to_name):
        hub = hubs.match(name)
        if hub is None:
            continue
        for m in messages.for_stop(hub.eva, leg.number):
            found.setdefault((m.code, m.kind), m)
    # Delay reason first, then quality notes.
    return sorted(found.values(), key=lambda m: m.kind != "delay")


def _score(
    arriving: Leg,
    departing: Leg,
    model: LoadedModel,
    hubs: HubMatcher,
    history: HistoryProvider,
    today: datetime,
) -> Transfer:
    arr_hub, dep_hub = hubs.match(arriving.to_name), hubs.match(departing.from_name)
    same_group = (
        arr_hub is not None and dep_hub is not None and arr_hub.group_eva == dep_hub.group_eva
    )
    hub = arr_hub if same_group else None
    t = Transfer(
        station=arriving.to_name,
        arriving=arriving,
        departing=departing,
        hub_eva=hub.group_eva if hub else None,
        planned_buffer=minutes(arriving.arr_planned, departing.dep_planned),
    )
    if arriving.cancelled or departing.cancelled:
        t.live_status, t.note = "cancelled", "cancelled"
        t.probability = 0.0
        return t
    if not (arriving.is_rail and departing.is_rail):
        # No score for buses, trams or underground lines: we have no history for
        # them. The live check still works when both have real-time data.
        t.note = "not_rail"
        if (
            arriving.arr_planned is not None
            and departing.dep_planned is not None
            and t.planned_buffer is not None
            and arriving.arr_planned.astimezone(BERLIN).date() == today.astimezone(BERLIN).date()
            and arriving.real_time
            and departing.real_time
        ):
            live = live_check(
                t.planned_buffer,
                arriving.arr_delay or 0,
                departing.dep_delay or 0,
                LOCAL_MIN_TRANSFER,
            )
            t.live_status, t.live_slack = live.status, live.remaining_slack_min
        return t
    if arriving.arr_planned is None or departing.dep_planned is None:
        return t

    cross_level = (
        same_group and arr_hub is not None and dep_hub is not None and arr_hub.eva != dep_hub.eva
    )
    inp = TransferInput.from_trains(
        arriving.arr_planned,
        departing.dep_planned,
        arriving.category,
        departing.category,
        cross_level,
    )
    if model.stage is not Stage.LIVE_ONLY:
        counts = history.counts(
            hub.group_eva if hub else None,
            arriving.number,
            departing.number,
            inp.in_group,
            inp.out_group,
            buffer_bucket(inp.planned_buffer_min),
        )
        s = score_transfer(model, inp, counts)
        t.probability, t.confidence = s.probability, s.confidence
        t.observations, t.early_estimate = s.observations, s.early_estimate

    same_day = arriving.arr_planned.astimezone(BERLIN).date() == today.astimezone(BERLIN).date()
    if same_day and arriving.real_time and departing.real_time:
        live = live_check(
            inp.planned_buffer_min,
            arriving.arr_delay or 0,
            departing.dep_delay or 0,
            inp.min_transfer_min,
        )
        t.live_status, t.live_slack = live.status, live.remaining_slack_min
    return t


def sort_journeys(journeys: list[Journey], by: str) -> list[Journey]:
    def arrival_key(j: Journey) -> float:
        return j.arrival.timestamp() if j.arrival else float("inf")

    if by == "reliable":
        return sorted(
            journeys,
            key=lambda j: (-(j.reliability if j.reliability is not None else -1), arrival_key(j)),
        )
    return sorted(journeys, key=arrival_key)

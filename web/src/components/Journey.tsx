import { useState } from "react";
import { sendFeedback } from "../lib/api";
import { store } from "../lib/storage";
import { useI18n } from "../i18n";
import { messageText } from "../i18n/messages";
import { Link } from "../lib/router";
import type { T } from "../i18n";
import { duration, hhmm } from "../lib/time";
import { pct, probabilityTone, transferTone } from "../lib/tone";
import type { Journey, Leg, Station, Tip, Transfer } from "../lib/types";
import { WatchPanel } from "./Watch";

function lineName(leg: Leg): string {
  if (leg.category && leg.number && leg.category.length + leg.number.length <= 9) {
    return /^[SU]$/.test(leg.category) ? `${leg.category}${leg.number}` : `${leg.category} ${leg.number}`;
  }
  return leg.line ?? leg.category ?? leg.mode;
}

const RAIL_MODES = new Set([
  "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL", "REGIONAL_RAIL", "SUBURBAN", "RAIL",
]);
const isRail = (leg: Leg) => RAIL_MODES.has(leg.mode);

function Delay({ min }: { min: number | null }) {
  if (min === null || min === 0) return null;
  return <span className={min > 0 ? "delay late" : "delay early"}>{min > 0 ? `+${min}` : min}</span>;
}

function Track({ actual, planned }: { actual: string | null; planned: string | null }) {
  const { t } = useI18n();
  if (!actual && !planned) return null;
  const changed = !!actual && !!planned && actual !== planned;
  return (
    <span className={changed ? "track changed" : "track"} title={changed ? t("results.trackChanged", { track: actual! }) : undefined}>
      {t("results.track", { track: actual ?? planned! })}
    </span>
  );
}

function confidenceText(t: T, tr: Transfer): string {
  const parts: string[] = [];
  if (tr.earlyEstimate) parts.push(t("score.earlyEstimate"));
  if (tr.confidence === "limited") parts.push(t("score.limitedData"));
  else if (tr.observations > 0) parts.push(t("score.basedOn", { count: tr.observations }));
  return parts.join(", ");
}

/** Asked once the connecting train has left (up to a day later), never before. */
function DidItWork({ tr, legIn, legOut }: { tr: Transfer; legIn: Leg; legOut: Leg }) {
  const { t } = useI18n();
  const dep = legOut.departurePlanned;
  const arr = legIn.arrivalPlanned;
  const key = `${tr.station}|${arr}|${dep}`;
  const [state, setState] = useState<"ask" | "sending" | "done" | "failed">(
    store.isAnswered(key) ? "done" : "ask",
  );
  if (!dep || !arr || !tr.station) return null;
  const since = Date.now() - Date.parse(dep);
  if (since < 0 || since > 24 * 3600 * 1000) return null;
  if (state === "done") return <p className="small muted">{t("feedback.thanks")}</p>;

  const answer = (made: boolean) => {
    setState("sending");
    sendFeedback({
      station: tr.station!,
      inTrain: lineName(legIn),
      outTrain: lineName(legOut),
      plannedArrival: arr,
      plannedDeparture: dep,
      made,
    })
      .then(() => {
        store.markAnswered(key);
        setState("done");
      })
      .catch(() => setState("failed"));
  };

  return (
    <div className="did-it-work">
      <p>{t("feedback.question")}</p>
      <div>
        <button type="button" className="ghost" disabled={state === "sending"} onClick={() => answer(true)}>
          {t("feedback.yes")}
        </button>
        <button type="button" className="ghost" disabled={state === "sending"} onClick={() => answer(false)}>
          {t("feedback.no")}
        </button>
      </div>
      {state === "failed" && <p className="error-text">{t("feedback.failed")}</p>}
    </div>
  );
}

function TransferNode({ tr, legIn, legOut }: { tr: Transfer; legIn: Leg; legOut: Leg }) {
  const { t } = useI18n();
  const tone = transferTone(tr);
  let reason: string | null = null;
  if (tr.note === "cancelled") reason = t("transfer.cancelled");
  else if (tr.note === "not_rail") reason = t("transfer.notRail");
  else if (!tr.recordedHub) reason = t("transfer.notRecorded");
  else if (tr.probability === null) reason = t("transfer.learning");

  return (
    <li className={`transfer tone-${tone}`}>
      <span className="node" aria-hidden="true" />
      <div className="transfer-body">
        <p className="transfer-head">
          <span>{t("transfer.at", { station: tr.station ?? "?" })}</span>
          {tr.plannedBufferMinutes !== null && <span className="buffer">{t("transfer.buffer", { min: tr.plannedBufferMinutes })}</span>}
        </p>
        {tr.probability !== null && tr.note !== "cancelled" && (
          <p className="chance">
            <strong className={`figure tone-${probabilityTone(tr.probability)}`}>{pct(tr.probability)} %</strong>
            <span>
              {t("transfer.chance")}
              {confidenceText(t, tr) && <small> ({confidenceText(t, tr)})</small>}
            </span>
          </p>
        )}
        {tr.liveStatus && (
          <p className={`live tone-${tone}`}>
            {t(`transfer.live.${tr.liveStatus}`, { min: Math.max(tr.liveSlackMinutes ?? 0, 0) })}
          </p>
        )}
        {reason && <p className="muted small">{reason}</p>}
        <DidItWork tr={tr} legIn={legIn} legOut={legOut} />
      </div>
    </li>
  );
}

function StopName({ name, hub }: { name: string | null; hub: number | null }) {
  if (!hub) return <span className="stop-name">{name}</span>;
  return (
    <Link className="stop-name" href={`/station?eva=${hub}`}>
      {name}
    </Link>
  );
}

function Forecast({ leg }: { leg: Leg }) {
  const { t } = useI18n();
  const f = leg.forecast;
  if (!f) return null;
  const vars = { typical: f.typical, high: f.high, count: f.trips };
  const key = f.high <= 1 ? "forecast.always" : f.typical <= 1 ? "forecast.onTime" : "forecast.late";
  return <p className="forecast small">{t(key, vars)}</p>;
}

function LegNotes({ leg }: { leg: Leg }) {
  const { t, lang } = useI18n();
  const notes = (leg.messages ?? [])
    .map((m) => ({ ...m, text: messageText(lang, m.code) }))
    .filter((m): m is typeof m & { text: string } => m.text !== null);
  if (!notes.length) return null;
  const delay = notes.find((m) => m.kind === "delay");
  const quality = notes.filter((m) => m.kind === "quality");
  return (
    <div className="leg-notes">
      {delay && <p className="reason">{t("results.reason", { text: delay.text })}</p>}
      {quality.length > 0 && (
        <ul className="quality">
          {quality.map((m) => (
            <li key={m.code}>{m.text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LegRow({ leg }: { leg: Leg }) {
  const { t } = useI18n();
  return (
    <li className={`leg${leg.cancelled ? " cancelled" : ""}`}>
      <div className="leg-stop">
        <time>{hhmm(leg.departurePlanned)}</time>
        <Delay min={leg.departureDelay} />
        <StopName name={leg.from} hub={leg.fromHub} />
        <Track actual={leg.departureTrack} planned={leg.departureTrackPlanned} />
      </div>
      <div className="leg-ride">
        <span className={`line-badge${isRail(leg) ? "" : " local"}`}>{lineName(leg)}</span>
        {leg.headsign && <span className="muted small">{t("results.towards", { headsign: leg.headsign })}</span>}
        {leg.cancelled && <span className="cancel-flag">{t("results.cancelled")}</span>}
      </div>
      <Forecast leg={leg} />
      <LegNotes leg={leg} />
      <div className="leg-stop">
        <time>{hhmm(leg.arrivalPlanned)}</time>
        <Delay min={leg.arrivalDelay} />
        <StopName name={leg.to} hub={leg.toHub} />
        <Track actual={leg.arrivalTrack} planned={leg.arrivalTrackPlanned} />
      </div>
    </li>
  );
}

/** "Take the earlier train" / "change elsewhere": shown on the card itself, not hidden in details. */
function Tips({ tips, onShow }: { tips: Tip[]; onShow: (tip: Tip) => void }) {
  const { t } = useI18n();
  if (!tips?.length) return null;
  return (
    <div className="tips">
      {tips.map((tip) => (
        <p key={tip.kind} className="tip">
          <span>
            {t(`tips.${tip.kind}`, {
              time: tip.departure ?? "",
              min: tip.minutes ?? 0,
              station: tip.station ?? "",
              arrival: tip.arrival ?? "",
              pct: pct(tip.reliability),
              old: pct(tip.previous),
            })}
          </span>
          {tip.departureIso && (
            <button type="button" className="link-button" onClick={() => onShow(tip)}>
              {t("tips.show")}
            </button>
          )}
        </p>
      ))}
    </div>
  );
}

export function JourneyCard({
  journey,
  from,
  to,
  local = false,
  onTip,
}: {
  journey: Journey;
  from?: Station;
  to?: Station;
  local?: boolean;
  onTip?: (tip: Tip) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const first = journey.legs[0];
  const last = journey.legs[journey.legs.length - 1];
  const depDelay = first?.departureDelay ?? null;
  const arrDelay = last?.arrivalDelay ?? null;
  const cancelled = journey.legs.some((l) => l.cancelled);
  const r = journey.reliability;
  const scored = journey.transfersCount === 0 || r !== null;

  return (
    <article className={`journey${cancelled ? " has-cancel" : ""}`}>
      <button type="button" className="journey-summary" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="times">
          <span className="time">
            {hhmm(first?.departurePlanned ?? journey.departure)}
            <Delay min={depDelay} />
          </span>
          <span className="route-bar" aria-hidden="true">
            {journey.transfers.map((tr, i) => (
              <span key={i} className={`dot tone-${transferTone(tr)}`} />
            ))}
          </span>
          <span className="time">
            {hhmm(last?.arrivalPlanned ?? journey.arrival)}
            <Delay min={arrDelay} />
          </span>
        </span>
        <span className="facts">
          <span className="ltr">{duration(journey.durationMinutes)}</span>
          <span>
            {journey.transfersCount === 0 ? t("results.direct") : t("results.transfers", { count: journey.transfersCount })}
          </span>
          <span className="lines">
            {journey.legs.map((l, i) => (
              <span key={i} className={`line-badge small${isRail(l) ? "" : " local"}`}>
                {lineName(l)}
              </span>
            ))}
          </span>
        </span>
        <span className="score">
          {scored && r !== null && journey.transfersCount > 0 ? (
            <>
              <strong className={`figure tone-${probabilityTone(r)}`}>{pct(r)} %</strong>
              <small>{t("results.reliability")}</small>
              {journey.reliabilityTrainsOnly && <small className="muted">{t("results.trainsOnly")}</small>}
            </>
          ) : journey.transfersCount > 0 && journey.transfers.every((x) => x.note === "not_rail") ? (
            <small className="muted">{t("results.liveOnly")}</small>
          ) : journey.transfersCount > 0 ? (
            <small className="muted">{t("results.noScoreYet")}</small>
          ) : null}
        </span>
      </button>
      <Tips tips={journey.tips} onShow={(tip) => onTip?.(tip)} />
      {open && (
        <ol className="itinerary">
          {journey.legs.flatMap((leg, i) => {
            const tr = journey.transfers[i];
            const rows = [<LegRow key={`l${i}`} leg={leg} />];
            const next = journey.legs[i + 1];
            if (tr && next) rows.push(<TransferNode key={`t${i}`} tr={tr} legIn={leg} legOut={next} />);
            return rows;
          })}
          {from && to && first?.departurePlanned && (
            <li className="watch-row">
              <WatchPanel from={from} to={to} departure={hhmm(first.departurePlanned)} local={local} />
            </li>
          )}
        </ol>
      )}
    </article>
  );
}

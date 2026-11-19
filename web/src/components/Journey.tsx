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

const LONG_DISTANCE = /^(ICE|IC|EC|ECE|RJ|RJX|NJ|EN|FLX|TGV|EST|WB)$/;

/** "ICE 579" for long-distance trains, the line ("S1", "RE 30", "Bus 253") for the rest.
 * Regional and S-Bahn trip numbers like "026719" mean nothing to travellers. */
function lineName(leg: Leg): string {
  const cat = leg.category ?? "";
  const line = leg.line?.trim();
  const number = leg.number?.replace(/^0+(?=\d)/, "");
  if (LONG_DISTANCE.test(cat) && number) return `${cat} ${number}`;
  if (line && line.length <= 8 && !/^\d{4,}$/.test(line)) {
    if (cat && !line.toUpperCase().startsWith(cat.toUpperCase()) && /^\d/.test(line)) {
      return /^[SU]$/.test(cat) ? `${cat}${line}` : `${cat} ${line}`;
    }
    const spaced = line.match(/^(RE|RB|IRE|MEX)\s*(\d+)$/i);
    return spaced ? `${spaced[1].toUpperCase()} ${spaced[2]}` : line;
  }
  if (cat && number) return /^[SU]$/.test(cat) ? `${cat}${number}` : `${cat} ${number}`;
  return line ?? (cat || leg.mode);
}

const RAIL_MODES = new Set([
  "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL", "REGIONAL_RAIL", "SUBURBAN", "RAIL",
]);
const isRail = (leg: Leg) => RAIL_MODES.has(leg.mode);

const privatePlace = (s: Station) => s.kind === "here" || s.kind === "address";
const metres = (m: number, lang: string) =>
  m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toLocaleString(lang, { maximumFractionDigits: 1 })} km`;
const km = (v: number, lang: string) => `${v < 10 ? v.toLocaleString(lang, { maximumFractionDigits: 1 }) : Math.round(v)} km`;

function WalkRow({ walk, text }: { walk: { meters: number; minutes: number }; text: string }) {
  const { t, lang } = useI18n();
  return (
    <li className="walk-row">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path
          d="M13 4.5a1.5 1.5 0 1 1 0 .01M10 21l2-6 2 2v4M8 11l3-3 3 1 2 3h3M11 8l-1 6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>
        {text}
        <span className="muted"> · {t("walk.amount", { distance: metres(walk.meters, lang), min: walk.minutes })}</span>
      </span>
    </li>
  );
}

function Delay({ min }: { min: number | null }) {
  if (min === null || min === 0) return null;
  return <span className={min > 0 ? "delay late" : "delay early"}>{min > 0 ? `+${min}` : min}</span>;
}

/** Buses and trams stop at a bay ("Steig"), trains at a platform ("Gleis"). */
const BAY_MODES = new Set(["BUS", "COACH", "TRAM", "CABLE_CAR", "AERIAL_LIFT", "FERRY"]);

function Track({ actual, planned, mode }: { actual: string | null; planned: string | null; mode: string }) {
  const { t } = useI18n();
  if (!actual && !planned) return null;
  const changed = !!actual && !!planned && actual !== planned;
  const bay = BAY_MODES.has(mode);
  const track = actual ?? planned!;
  const changedText = bay ? t("results.standChanged", { track }) : t("results.trackChanged", { track });
  return (
    <span className={changed ? "track changed" : "track"} title={changed ? changedText : undefined}>
      {bay ? t("results.stand", { track }) : t("results.track", { track })}
      {changed && <span className="sr-only"> ({changedText})</span>}
    </span>
  );
}

function rideMinutes(leg: Leg): number | null {
  if (!leg.departurePlanned || !leg.arrivalPlanned) return null;
  return Math.round((Date.parse(leg.arrivalPlanned) - Date.parse(leg.departurePlanned)) / 60_000);
}

/** "12 Min. · 5 Zwischenhalte", and the stops themselves when opened. */
function Ride({ leg }: { leg: Leg }) {
  const { t } = useI18n();
  const min = rideMinutes(leg);
  const stops = leg.stops ?? [];
  const ride = min !== null && min > 0 ? t("results.ride", { min }) : null;
  if (!stops.length) return ride ? <p className="ride small muted">{ride}</p> : null;
  return (
    <details className="ride small">
      <summary className="muted">
        {ride && <>{ride} · </>}
        {t("results.stops", { count: stops.length })}
      </summary>
      <ol className="stop-list">
        {stops.map((st, i) => (
          <li key={`${st.name}-${i}`} className={st.cancelled ? "cancelled" : undefined}>
            <time>{st.time ? hhmm(st.time) : ""}</time>
            <span>{st.name}</span>
            {st.track && (
              <span className="track">
                {BAY_MODES.has(leg.mode) ? t("results.stand", { track: st.track }) : t("results.track", { track: st.track })}
              </span>
            )}
          </li>
        ))}
      </ol>
    </details>
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
        <Track actual={leg.departureTrack} planned={leg.departureTrackPlanned} mode={leg.mode} />
      </div>
      <div className="leg-ride">
        <span className={`line-badge${isRail(leg) ? "" : " local"}`}>{lineName(leg)}</span>
        {leg.headsign && <span className="muted small">{t("results.towards", { headsign: leg.headsign })}</span>}
        {leg.cancelled && <span className="cancel-flag">{t("results.cancelled")}</span>}
      </div>
      <Ride leg={leg} />
      <Forecast leg={leg} />
      <LegNotes leg={leg} />
      <div className="leg-stop">
        <time>{hhmm(leg.arrivalPlanned)}</time>
        <Delay min={leg.arrivalDelay} />
        <StopName name={leg.to} hub={leg.toHub} />
        <Track actual={leg.arrivalTrack} planned={leg.arrivalTrackPlanned} mode={leg.mode} />
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
  const { t, lang } = useI18n();
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
          {/* With a walk, the summary shows when to leave and when you are there, so
              the times match the total duration. Train delays stay in the details. */}
          <span className="time">
            {journey.walkStart ? hhmm(journey.departure) : hhmm(first?.departurePlanned ?? journey.departure)}
            {!journey.walkStart && <Delay min={depDelay} />}
          </span>
          <span className="route-bar" aria-hidden="true">
            {journey.transfers.map((tr, i) => (
              <span key={i} className={`dot tone-${transferTone(tr)}`} />
            ))}
          </span>
          <span className="time">
            {journey.walkEnd ? hhmm(journey.arrival) : hhmm(last?.arrivalPlanned ?? journey.arrival)}
            {!journey.walkEnd && <Delay min={arrDelay} />}
          </span>
        </span>
        <span className="facts">
          <span className="ltr">{duration(journey.durationMinutes)}</span>
          <span>
            {journey.transfersCount === 0 ? t("results.direct") : t("results.transfers", { count: journey.transfersCount })}
          </span>
          {journey.distanceKm !== null && journey.distanceKm !== undefined && (
            <span className="ltr">{km(journey.distanceKm, lang)}</span>
          )}
          {journey.walkMeters >= 100 && (
            <span>{t("walk.total", { distance: metres(journey.walkMeters, lang) })}</span>
          )}
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
          {journey.walkStart && first && (
            <WalkRow walk={journey.walkStart} text={t("walk.toStop", { stop: first.from ?? "" })} />
          )}
          {journey.legs.flatMap((leg, i) => {
            const tr = journey.transfers[i];
            const rows = [<LegRow key={`l${i}`} leg={leg} />];
            const next = journey.legs[i + 1];
            if (tr && next) rows.push(<TransferNode key={`t${i}`} tr={tr} legIn={leg} legOut={next} />);
            return rows;
          })}
          {journey.walkEnd && last && (
            <WalkRow walk={journey.walkEnd} text={t("walk.fromStop", { stop: last.to ?? "" })} />
          )}
          {/* No daily check from "Mein Standort" or an address: it would store a position on the server. */}
          {from && to && !privatePlace(from) && !privatePlace(to) && first?.departurePlanned && (
            <li className="watch-row">
              <WatchPanel from={from} to={to} departure={hhmm(first.departurePlanned)} local={local} />
            </li>
          )}
        </ol>
      )}
    </article>
  );
}

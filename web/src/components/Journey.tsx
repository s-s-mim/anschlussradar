import { useState } from "react";
import { useI18n } from "../i18n";
import type { T } from "../i18n";
import { duration, hhmm } from "../lib/time";
import { pct, probabilityTone, transferTone } from "../lib/tone";
import type { Journey, Leg, Transfer } from "../lib/types";

function lineName(leg: Leg): string {
  if (leg.category && leg.number && leg.category.length + leg.number.length <= 9) {
    return /^[SU]$/.test(leg.category) ? `${leg.category}${leg.number}` : `${leg.category} ${leg.number}`;
  }
  return leg.line ?? leg.category ?? leg.mode;
}

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

function TransferNode({ tr }: { tr: Transfer }) {
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
      </div>
    </li>
  );
}

function LegRow({ leg }: { leg: Leg }) {
  const { t } = useI18n();
  return (
    <li className={`leg${leg.cancelled ? " cancelled" : ""}`}>
      <div className="leg-stop">
        <time>{hhmm(leg.departurePlanned)}</time>
        <Delay min={leg.departureDelay} />
        <span className="stop-name">{leg.from}</span>
        <Track actual={leg.departureTrack} planned={leg.departureTrackPlanned} />
      </div>
      <div className="leg-ride">
        <span className="line-badge">{lineName(leg)}</span>
        {leg.headsign && <span className="muted small">{t("results.towards", { headsign: leg.headsign })}</span>}
        {leg.cancelled && <span className="cancel-flag">{t("results.cancelled")}</span>}
      </div>
      <div className="leg-stop">
        <time>{hhmm(leg.arrivalPlanned)}</time>
        <Delay min={leg.arrivalDelay} />
        <span className="stop-name">{leg.to}</span>
        <Track actual={leg.arrivalTrack} planned={leg.arrivalTrackPlanned} />
      </div>
    </li>
  );
}

export function JourneyCard({ journey }: { journey: Journey }) {
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
          <span>{duration(journey.durationMinutes)}</span>
          <span>
            {journey.transfersCount === 0 ? t("results.direct") : t("results.transfers", { count: journey.transfersCount })}
          </span>
          <span className="lines">
            {journey.legs.map((l, i) => (
              <span key={i} className="line-badge small">
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
            </>
          ) : journey.transfersCount > 0 ? (
            <small className="muted">{t("results.noScoreYet")}</small>
          ) : null}
        </span>
      </button>
      {open && (
        <ol className="itinerary">
          {journey.legs.flatMap((leg, i) => {
            const tr = journey.transfers[i];
            const rows = [<LegRow key={`l${i}`} leg={leg} />];
            if (tr) rows.push(<TransferNode key={`t${i}`} tr={tr} />);
            return rows;
          })}
        </ol>
      )}
    </article>
  );
}

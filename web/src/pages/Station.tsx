// Station page: next departures and punctuality by hour of day at a recorded hub.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { messageText } from "../i18n/messages";
import { ApiError, getBoard } from "../lib/api";
import { Link } from "../lib/router";
import { hhmm } from "../lib/time";
import { BANDS, pct, punctualityBand } from "../lib/tone";
import type { Board, BoardDeparture, HourStat } from "../lib/types";

/** "S1" for S-Bahn and U-Bahn, "RE 30" for regional lines, "ICE 579" otherwise. */
function trainName(d: BoardDeparture): string {
  const cat = d.category ?? "";
  // Some feeds already put the category in the line ("RE6"): never "RE RE6".
  if (d.line && cat && d.line.toUpperCase().startsWith(cat.toUpperCase())) return d.line;
  if (/^[SU]$/.test(cat) && d.line) return `${cat}${d.line}`;
  if (/^(RE|RB|IRE|MEX)$/.test(cat) && d.line) return `${cat} ${d.line}`;
  return [cat, d.number].filter(Boolean).join(" ");
}

function DepartureRow({ d }: { d: BoardDeparture }) {
  const { t, lang } = useI18n();
  const changed = !!d.platform && !!d.platformPlanned && d.platform !== d.platformPlanned;
  const reason = d.messages.find((m) => m.kind === "delay");
  const reasonText = reason ? messageText(lang, reason.code) : null;
  return (
    <li className={d.cancelled ? "dep cancelled" : "dep"}>
      <span className="dep-time">
        <time>{hhmm(d.departurePlanned)}</time>
        {d.delay !== null && d.delay !== 0 && (
          <span className={d.delay > 0 ? "delay late" : "delay early"}>{d.delay > 0 ? `+${d.delay}` : d.delay}</span>
        )}
      </span>
      <span className="dep-main">
        {d.lineId ? (
          <Link className="line-badge" href={`/line?id=${d.lineId}`}>
            {trainName(d)}
          </Link>
        ) : (
          <span className="line-badge">{trainName(d)}</span>
        )} <span className="dep-dest">{d.destination}</span>
        {d.cancelled && <span className="cancel-flag"> {t("results.cancelled")}</span>}
        {reasonText && <span className="dep-reason">{t("results.reason", { text: reasonText })}</span>}
      </span>
      {d.platform && (
        <span className={changed ? "track changed" : "track"}>
          {t("results.track", { track: d.platform })}
          {changed && <span className="track-note">{t("board.platformChanged")}</span>}
        </span>
      )}
    </li>
  );
}

/** 24 bars, one per hour; the height is the share of punctual departures. */
export function HourlyChart({ hours }: { hours: HourStat[] }) {
  const { t } = useI18n();
  const [picked, setPicked] = useState<number | null>(null);
  const known = (h: HourStat) => h.onTime !== null && h.departures >= 10;
  const text = (h: HourStat) =>
    known(h)
      ? t("board.bar", { hour: h.hour, pct: pct(h.onTime!), count: h.departures })
      : `${h.hour}:00: ${t("board.noData")}`;
  if (!hours.some(known)) return <p className="notice">{t("board.notEnough")}</p>;
  const current = hours.find((h) => h.hour === picked);
  return (
    <figure className="hourly">
      <ol className="bars">
        {hours.map((h) => (
          <li key={h.hour}>
            <button
              type="button"
              className={picked === h.hour ? "bar-hit on" : "bar-hit"}
              aria-label={text(h)}
              aria-pressed={picked === h.hour}
              onClick={() => setPicked(picked === h.hour ? null : h.hour)}
            >
              <span
                className={known(h) ? `bar band-${punctualityBand(h.onTime)}` : "bar empty"}
                style={{ height: known(h) ? `${Math.max(4, h.onTime! * 100)}%` : "4%" }}
              />
            </button>
            {h.hour % 3 === 0 && <span className="tick">{h.hour}</span>}
          </li>
        ))}
      </ol>
      <p className="small bar-readout" aria-live="polite">
        {current ? text(current) : t("board.tapBar")}
      </p>
      <figcaption>
        <ul className="legend">
          {BANDS.map((b) => (
            <li key={b}>
              <span className={`swatch band-${b}`} aria-hidden="true" />
              {b === "none" ? t("board.fewDepartures") : t(`network.band.${b}`)}
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

export function Station({ search }: { search: URLSearchParams }) {
  const { t } = useI18n();
  const eva = Number(search.get("eva"));
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isInteger(eva) || eva <= 0) {
      setError(t("board.unknown"));
      return;
    }
    const ctrl = new AbortController();
    const load = () =>
      getBoard(eva, ctrl.signal)
        .then((b) => {
          setBoard(b);
          setError(null);
          document.title = `${b.name} – AnschlussRadar`;
        })
        .catch((e: unknown) => {
          if (ctrl.signal.aborted) return;
          setError(e instanceof ApiError && e.status === 404 ? t("board.unknown") : t("board.unavailable"));
        });
    load();
    const timer = setInterval(load, 60_000); // the board refreshes itself every minute
    return () => {
      ctrl.abort();
      clearInterval(timer);
    };
  }, [eva, t]);

  return (
    <div className="page wrap narrow station-page">
      <p className="small">
        <Link href="/stations">{t("nav.stations")}</Link>
      </p>
      <h1>{board?.name ?? "…"}</h1>
      {error && <p className="notice error">{error}</p>}
      {board && (
        <>
          <section>
            <h2>
              {t("board.title")} <small className="muted">{t("board.window")}</small>
            </h2>
            {board.departures.length === 0 ? (
              <p className="notice">{board.available ? t("board.none") : t("board.unavailable")}</p>
            ) : (
              <ol className="departures">
                {board.departures.map((d, i) => (
                  <DepartureRow key={`${d.departurePlanned}-${d.number}-${i}`} d={d} />
                ))}
              </ol>
            )}
          </section>
          <section>
            <h2>{t("board.hourly")}</h2>
            <p className="small muted">{t("board.hourlyLead")}</p>
            <HourlyChart hours={board.hourly} />
          </section>
        </>
      )}
    </div>
  );
}

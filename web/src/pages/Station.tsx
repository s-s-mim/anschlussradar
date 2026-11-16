// Station page: next departures and punctuality by hour of day at a recorded hub.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { messageText } from "../i18n/messages";
import { ApiError, getBoard } from "../lib/api";
import { Link } from "../lib/router";
import { hhmm } from "../lib/time";
import { pct, probabilityTone } from "../lib/tone";
import type { Board, BoardDeparture, HourStat } from "../lib/types";

/** "S1" for S-Bahn and U-Bahn, "RE 30" for regional lines, "ICE 579" otherwise. */
function trainName(d: BoardDeparture): string {
  const cat = d.category ?? "";
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
        <span className="line-badge">{trainName(d)}</span> <span className="dep-dest">{d.destination}</span>
        {d.cancelled && <span className="cancel-flag"> {t("results.cancelled")}</span>}
        {reasonText && <span className="dep-reason">{t("results.reason", { text: reasonText })}</span>}
      </span>
      {d.platform && (
        <span className={changed ? "track changed" : "track"}>{t("results.track", { track: d.platform })}</span>
      )}
    </li>
  );
}

/** 24 bars, one per hour; the height is the share of punctual departures. */
function HourlyChart({ hours }: { hours: HourStat[] }) {
  const { t } = useI18n();
  return (
    <figure className="hourly">
      <ol className="bars">
        {hours.map((h) => {
          const known = h.onTime !== null && h.departures >= 10;
          const label = known
            ? t("board.bar", { hour: h.hour, pct: pct(h.onTime!), count: h.departures })
            : `${h.hour}:00: ${t("board.noData")}`;
          return (
            <li key={h.hour} title={label} aria-label={label}>
              <span
                className={known ? `bar tone-${probabilityTone(h.onTime)}` : "bar empty"}
                style={{ height: known ? `${Math.max(4, h.onTime! * 100)}%` : "4%" }}
              />
              {h.hour % 3 === 0 && <span className="tick">{h.hour}</span>}
            </li>
          );
        })}
      </ol>
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

// One line: its recorded stations in running order and punctuality by hour.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { ApiError, getLine } from "../lib/api";
import { Link } from "../lib/router";
import { pct, probabilityTone } from "../lib/tone";
import type { LineDetail } from "../lib/types";
import { HourlyChart } from "./Station";

export function Line({ search }: { search: URLSearchParams }) {
  const { t, lang } = useI18n();
  const id = search.get("id") ?? "";
  const [line, setLine] = useState<LineDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getLine(id, ctrl.signal)
      .then((l) => {
        setLine(l);
        document.title = `${l.name} – AnschlussRadar`;
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof ApiError && e.status === 404 ? t("lines.unknown") : t("lines.unavailable"));
      });
    return () => ctrl.abort();
  }, [id, t]);

  return (
    <div className="page wrap narrow line-page">
      <p className="small">
        <Link href="/lines">{t("nav.lines")}</Link>
      </p>
      <h1>
        {line ? <span className="line-badge big">{line.name}</span> : "…"}
        {line && line.terminals.length > 0 && <span className="line-ends">{line.terminals.join(" – ")}</span>}
      </h1>
      {error && <p className="notice error">{error}</p>}
      {line && (
        <>
          {line.onTime !== null && (
            <p className="chance">
              <strong className={`figure tone-${probabilityTone(line.onTime)}`}>{pct(line.onTime)} %</strong>
              <span>{t("lines.overall", { days: line.days, count: line.departures })}</span>
            </p>
          )}

          <section>
            <h2>{t("lines.stations")}</h2>
            <p className="small muted">{t("lines.partNote")}</p>
            <ol className="line-stops">
              {line.stations.map((s) => (
                <li key={s.eva}>
                  <span className="node" aria-hidden="true" />
                  <Link href={`/station?eva=${s.eva}`}>{s.name}</Link>
                  <span className="small muted">
                    {s.onTime === null
                      ? t("board.noData")
                      : t("lines.stationRow", { pct: pct(s.onTime), delay: (s.avgDelay ?? 0).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) })}
                  </span>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h2>{t("board.hourly")}</h2>
            <p className="small muted">{t("lines.hourlyLead", { days: line.days })}</p>
            <HourlyChart hours={line.hourly} />
          </section>
        </>
      )}
    </div>
  );
}

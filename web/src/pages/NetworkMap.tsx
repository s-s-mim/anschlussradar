import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { getNetwork } from "../lib/api";
import { MAP_HEIGHT, MAP_WIDTH, STATES, project } from "../lib/germanyMap";
import { Link, navigate } from "../lib/router";
import type { NetworkStation, NetworkWindow } from "../lib/types";

type Span = "now" | "week";
type Band = "good" | "fair" | "risk" | "bad" | "none";

// Share of departures less than 6 minutes late. Long-distance trains in Germany
// manage about two thirds, regional trains about nine in ten.
function band(w: NetworkWindow): Band {
  if (w.onTime === null) return "none";
  if (w.onTime >= 0.9) return "good";
  if (w.onTime >= 0.8) return "fair";
  if (w.onTime >= 0.65) return "risk";
  return "bad";
}

const BANDS: Band[] = ["good", "fair", "risk", "bad", "none"];

export function NetworkMap() {
  const { t } = useI18n();
  const [stations, setStations] = useState<NetworkStation[] | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "off" | "failed">("loading");
  const [span, setSpan] = useState<Span>("now");

  useEffect(() => {
    getNetwork()
      .then((n) => {
        setStations(n.stations);
        setState(n.available ? "ok" : "off");
      })
      .catch(() => setState("failed"));
  }, []);

  const label = (s: NetworkStation) => {
    const w = s[span];
    return w.onTime === null
      ? t("network.dotNoData", { name: s.name })
      : t("network.dot", { name: s.name, pct: Math.round(w.onTime * 100), count: w.departures });
  };

  // Small stations first, so the big ones are drawn on top.
  const drawn = [...(stations ?? [])].sort((a, b) => Number(a.national) - Number(b.national));
  const worst = (stations ?? [])
    .filter((s) => s[span].onTime !== null)
    .sort((a, b) => a[span].onTime! - b[span].onTime!)
    .slice(0, 5);

  return (
    <div className="page wrap narrow network">
      <h1>{t("network.title")}</h1>
      <p className="lead">{t("network.lead")}</p>

      <div className="segmented" role="radiogroup" aria-label={t("network.span")}>
        <button type="button" role="radio" aria-checked={span === "now"} onClick={() => setSpan("now")}>
          {t("network.now")}
        </button>
        <button type="button" role="radio" aria-checked={span === "week"} onClick={() => setSpan("week")}>
          {t("network.week")}
        </button>
      </div>

      {state === "loading" && (
        <div className="loading" role="status">
          <span />
          <span />
          <span />
        </div>
      )}
      {(state === "failed" || state === "off") && <p className="notice">{t("network.unavailable")}</p>}

      <figure className="map">
        <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label={t("network.title")}>
          <g className="states">
            {STATES.map((s) => (
              <path key={s.name} d={s.d} />
            ))}
          </g>
          {state === "ok" &&
            drawn.map((s) => {
              const [x, y] = project(s.lat, s.lon);
              const r = s.national ? 8 : 6;
              return (
                <a
                  key={s.eva}
                  href={`/station?eva=${s.eva}`}
                  aria-label={label(s)}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`/station?eva=${s.eva}`);
                  }}
                >
                  <title>{label(s)}</title>
                  <circle cx={x} cy={y} r={16} className="hit" />
                  <circle cx={x} cy={y} r={r} className={`stop band-${band(s[span])}`} />
                </a>
              );
            })}
        </svg>
        <figcaption>
          <p className="small muted">{t("network.legendTitle")}</p>
          <ul className="legend">
            {BANDS.map((b) => (
              <li key={b}>
                <span className={`swatch band-${b}`} aria-hidden="true" />
                {t(`network.band.${b}`)}
              </li>
            ))}
          </ul>
        </figcaption>
      </figure>

      {worst.length > 0 && (
        <section>
          <h2>{t("network.worst")}</h2>
          <ol className="worst">
            {worst.map((s) => (
              <li key={s.eva}>
                <Link href={`/station?eva=${s.eva}`}>{s.name}</Link>
                <span className={`figure tone-${band(s[span])}`}>{Math.round(s[span].onTime! * 100)} %</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <p className="small">
        <Link href="/stations">{t("network.allStations")}</Link>
      </p>
    </div>
  );
}

// All regional and S-Bahn lines seen at the recorded stations, with a filter.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { getLines } from "../lib/api";
import { Link } from "../lib/router";
import { pct, probabilityTone } from "../lib/tone";
import type { LineSummary } from "../lib/types";

/** Lower case without accents and spaces, so "re30" finds "RE 30" and "muenchen" finds "München". */
function normalizeText(s: string): string {
  return s
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/g, "");
}

export function Lines() {
  const { t } = useI18n();
  const [lines, setLines] = useState<LineSummary[] | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "off" | "failed">("loading");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    getLines()
      .then((r) => {
        setLines(r.lines);
        setState(r.available ? "ok" : "off");
      })
      .catch(() => setState("failed"));
  }, []);

  const q = normalizeText(filter);
  const shown = (lines ?? []).filter(
    (l) => !q || normalizeText(`${l.name} ${l.terminals.join(" ")}`).includes(q),
  );
  const groups = new Map<string, LineSummary[]>();
  for (const l of shown) groups.set(l.category, [...(groups.get(l.category) ?? []), l]);

  return (
    <div className="page wrap narrow lines-page">
      <h1>{t("lines.title")}</h1>
      <p className="lead">{t("lines.lead", { days: 28 })}</p>

      {state === "loading" && (
        <div className="loading" role="status">
          <span />
          <span />
          <span />
        </div>
      )}
      {(state === "failed" || state === "off") && <p className="notice">{t("lines.unavailable")}</p>}

      {state === "ok" && (
        <>
          <div className="field">
            <label htmlFor="line-filter">{t("lines.filter")}</label>
            <input
              id="line-filter"
              type="search"
              value={filter}
              placeholder={t("lines.filterHint")}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <p className="small muted" role="status">
            {t("lines.count", { count: shown.length })}
          </p>
          {[...groups.entries()].map(([cat, list]) => (
            <section key={cat}>
              <h2 className="line-group">{cat}</h2>
              <ul className="line-list">
                {list.map((l) => (
                  <li key={l.id}>
                    <Link href={`/line?id=${l.id}`}>
                      <span className="line-badge">{l.name}</span>
                      <span className="line-ends">{l.terminals.join(" – ")}</span>
                      {l.onTime !== null && (
                        <span className={`line-share tone-${probabilityTone(l.onTime)}`}>{pct(l.onTime)} %</span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}
    </div>
  );
}

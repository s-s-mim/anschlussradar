import { useEffect, useMemo, useState } from "react";
import { JourneyCard } from "../components/Journey";
import { LearningBanner } from "../components/LearningBanner";
import { useI18n } from "../i18n";
import { ApiError, findJourneys } from "../lib/api";
import { fromParams, place, toParams } from "../lib/query";
import type { Search } from "../lib/query";
import { Link, navigate } from "../lib/router";
import { store } from "../lib/storage";
import { addMinutes, berlinIso, berlinNow } from "../lib/time";
import type { Journey, JourneysResponse, Stage } from "../lib/types";

type Sort = "fastest" | "reliable";

function sortJourneys(list: Journey[], by: Sort): Journey[] {
  const arr = (j: Journey) => (j.arrival ? Date.parse(j.arrival) : Infinity);
  const copy = [...list];
  if (by === "fastest") return copy.sort((a, b) => arr(a) - arr(b));
  return copy.sort((a, b) => (b.reliability ?? -1) - (a.reliability ?? -1) || arr(a) - arr(b));
}

export function Results({ search, onStage }: { search: URLSearchParams; onStage: (s: Stage) => void }) {
  const { t, lang } = useI18n();
  const parsed = fromParams(search);
  const key = search.toString();
  const [data, setData] = useState<JourneysResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<Sort>("fastest");
  const [attempt, setAttempt] = useState(0);
  const valid = !!(parsed.from && parsed.to);
  const route = valid ? { from: parsed.from!, to: parsed.to! } : null;
  const [saved, setSaved] = useState(route ? store.isSaved(route) : false);
  const now = berlinNow();
  const s: Search | null = route
    ? { ...route, date: parsed.date ?? now.date, time: parsed.time ?? now.time, arriveBy: !!parsed.arriveBy }
    : null;

  useEffect(() => {
    if (!s) return;
    store.addRecent({ from: s.from, to: s.to });
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    findJourneys(
      { from: place(s.from), to: place(s.to), time: berlinIso(s.date, s.time), arriveBy: s.arriveBy },
      ctrl.signal,
    )
      .then((res) => {
        setData(res);
        onStage(res.stage);
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        const code = e instanceof ApiError ? e.code : "unknown";
        setError(code === "offline" ? t("errors.offline") : code === "planner_unavailable" ? t("errors.planner") : t("errors.generic"));
        setData(null);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [key, attempt]);

  useEffect(() => {
    if (!valid) navigate("/", true);
  }, [valid]);

  const journeys = useMemo(() => (data ? sortJourneys(data.journeys, sort) : []), [data, sort]);

  if (!s) return null;

  const shift = (dir: -1 | 1) => {
    const times = (data?.journeys ?? []).map((j) => j.departure).filter((x): x is string => !!x).sort();
    const base = dir === 1 ? times[times.length - 1] : times[0];
    const next = base ? addMinutes(base, dir === 1 ? 1 : -60) : addMinutes(berlinIso(s.date, s.time), dir * 60);
    navigate(`/connections?${toParams({ ...s, date: next.date, time: next.time, arriveBy: false })}`);
  };

  const dateLabel = new Intl.DateTimeFormat(lang, { weekday: "short", day: "numeric", month: "short" }).format(
    new Date(`${s.date}T12:00:00`),
  );

  return (
    <div className="results wrap">
      <header className="results-head">
        <h1>
          {s.from.name} <span className="arrow" aria-hidden="true">→</span> {s.to.name}
        </h1>
        <p className="muted">
          {s.arriveBy ? t("home.arrival") : t("home.departure")} {dateLabel}, {s.time}
        </p>
        <Link className="change" href={`/?${toParams(s)}`}>
          {t("results.change")}
        </Link>
        <button
          type="button"
          className={saved ? "save on" : "save"}
          aria-pressed={saved}
          onClick={() => setSaved(store.toggleSaved({ from: s.from, to: s.to }))}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
          {saved ? t("results.unsave") : t("results.save")}
        </button>
      </header>

      <LearningBanner stage={data?.stage ?? null} />

      <div className="toolbar">
        <div className="segmented" role="radiogroup" aria-label={t("results.sortLabel")}>
          <button type="button" role="radio" aria-checked={sort === "fastest"} onClick={() => setSort("fastest")}>
            {t("results.fastest")}
          </button>
          <button type="button" role="radio" aria-checked={sort === "reliable"} onClick={() => setSort("reliable")}>
            {t("results.reliable")}
          </button>
        </div>
      </div>

      <button type="button" className="ghost shift" onClick={() => shift(-1)} disabled={loading}>
        {t("results.earlier")}
      </button>

      {loading && <div className="loading" role="status" aria-label={t("home.searching")}><span /><span /><span /></div>}
      {!loading && error && (
        <div className="notice error" role="alert">
          <p>{error}</p>
          <button type="button" className="ghost" onClick={() => setAttempt((a) => a + 1)}>
            {t("errors.retry")}
          </button>
        </div>
      )}
      {!loading && !error && journeys.length === 0 && <p className="notice">{t("results.none")}</p>}
      {!loading && !error && journeys.length > 0 && (
        <div className="journeys">
          {journeys.map((j, i) => (
            <JourneyCard key={`${j.departure}-${j.arrival}-${i}`} journey={j} from={s.from} to={s.to} />
          ))}
        </div>
      )}

      <button type="button" className="ghost shift" onClick={() => shift(1)} disabled={loading}>
        {t("results.later")}
      </button>

      <p className="attribution small muted">
        <a href="https://transitous.org/sources/" target="_blank" rel="noopener noreferrer">
          {t("results.attribution")}
        </a>
      </p>
    </div>
  );
}

import { useState } from "react";
import type { FormEvent } from "react";
import { LearningBanner } from "../components/LearningBanner";
import { NearMe } from "../components/NearMe";
import { StationInput } from "../components/StationInput";
import { AnsweredHint } from "../components/QuestionBox";
import { WatchedList } from "../components/WatchedList";
import { WhyList } from "../components/Why";
import { useI18n } from "../i18n";
import { fromParams, toParams } from "../lib/query";
import { Link, navigate } from "../lib/router";
import { store } from "../lib/storage";
import type { Route } from "../lib/storage";
import { berlinNow } from "../lib/time";
import type { Stage, Station } from "../lib/types";

export function Home({ search, stage }: { search: URLSearchParams; stage: Stage | null }) {
  const { t } = useI18n();
  const newVisitor = !store.hasSearched();
  const initial = fromParams(search);
  const now = berlinNow();
  const [from, setFrom] = useState<Station | null>(initial.from ?? null);
  const [to, setTo] = useState<Station | null>(initial.to ?? null);
  const [date, setDate] = useState(initial.date ?? now.date);
  const [time, setTime] = useState(initial.time ?? now.time);
  const [arriveBy, setArriveBy] = useState(initial.arriveBy ?? false);
  const [local, setLocal] = useState(initial.local ?? store.local());
  const [tried, setTried] = useState(false);
  const [saved, setSaved] = useState<Route[]>(store.saved);
  const recent = store.recent().filter((r) => !saved.some((s) => s.from.id === r.from.id && s.to.id === r.to.id));

  const go = (f: Station, t2: Station, d = date, h = time, a = arriveBy) =>
    navigate(`/connections?${toParams({ from: f, to: t2, date: d, time: h, arriveBy: a, local })}`);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (from && to) go(from, to);
  };

  const quick = (r: Route) => {
    const n = berlinNow();
    go(r.from, r.to, n.date, n.time, false);
  };

  return (
    <div className="home">
      <section className="hero wrap">
        <h1>{t("home.title")}</h1>
        <p className="lead">{t("home.lead")}</p>
      </section>

      <div className="wrap">
        <LearningBanner stage={stage} />
        <AnsweredHint />
        <form className="search" onSubmit={submit} noValidate>
          <div className="stations">
            <div className="from-field">
              <StationInput label={t("home.from")} value={from} onChange={setFrom} invalid={tried && !from} />
              <NearMe onPick={setFrom} />
            </div>
            <button
              type="button"
              className="swap"
              onClick={() => {
                setFrom(to);
                setTo(from);
              }}
              aria-label={t("home.swap")}
              title={t("home.swap")}
            >
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path d="M7 4v14m0 0-3-3m3 3 3-3M17 20V6m0 0-3 3m3-3 3 3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <StationInput label={t("home.to")} value={to} onChange={setTo} invalid={tried && !to} />
          </div>
          {tried && (!from || !to) && <p className="error-text">{t("home.pickStation")}</p>}

          <div className="when">
            <div className="segmented" role="radiogroup" aria-label={t("home.time")}>
              <button type="button" role="radio" aria-checked={!arriveBy} onClick={() => setArriveBy(false)}>
                {t("home.departure")}
              </button>
              <button type="button" role="radio" aria-checked={arriveBy} onClick={() => setArriveBy(true)}>
                {t("home.arrival")}
              </button>
            </div>
            <div className="field">
              <label htmlFor="date">{t("home.date")}</label>
              <input id="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="time">{t("home.time")}</label>
              <input id="time" type="time" value={time} onChange={(e) => setTime(e.target.value)} required />
            </div>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                const n = berlinNow();
                setDate(n.date);
                setTime(n.time);
                setArriveBy(false);
              }}
            >
              {t("home.now")}
            </button>
          </div>

          <label className="check">
            <input
              type="checkbox"
              checked={local}
              onChange={(e) => {
                setLocal(e.target.checked);
                store.setLocal(e.target.checked);
              }}
            />
            <span>{t("home.local")}</span>
          </label>

          <button type="submit" className="primary">
            {t("home.search")}
          </button>
        </form>

        {newVisitor ? (
          <section className="why" aria-labelledby="why-title">
            <h2 id="why-title">{t("home.whyTitle")}</h2>
            <WhyList limit={4} />
            <p className="small">
              <Link href="/about#anders">{t("home.whyMore")}</Link>
            </p>
          </section>
        ) : (
          <p className="why-link small">
            <Link href="/about#anders">{t("home.whyLink")}</Link>
          </p>
        )}

        <WatchedList />

        {saved.length > 0 && (
          <section className="routes">
            <h2>{t("home.saved")}</h2>
            <ul>
              {saved.map((r) => (
                <li key={`${r.from.id}|${r.to.id}`}>
                  <button type="button" className="route-link" onClick={() => quick(r)}>
                    {r.from.name} <span aria-hidden="true">→</span> {r.to.name}
                  </button>
                  <button
                    type="button"
                    className="remove"
                    aria-label={`${t("home.remove")}: ${r.from.name} – ${r.to.name}`}
                    onClick={() => {
                      store.toggleSaved(r);
                      setSaved(store.saved());
                    }}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {recent.length > 0 && (
          <section className="routes">
            <h2>{t("home.recent")}</h2>
            <ul>
              {recent.map((r) => (
                <li key={`${r.from.id}|${r.to.id}`}>
                  <button type="button" className="route-link" onClick={() => quick(r)}>
                    {r.from.name} <span aria-hidden="true">→</span> {r.to.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

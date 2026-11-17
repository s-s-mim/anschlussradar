// "Was AnschlussRadar anders macht": the first points on the start page, all of them on the
// About page. Only features that are live go in here; "Bald verfügbar" lists the rest.
import { useI18n } from "../i18n";
import type { Stage } from "../lib/types";

export function WhyList({ limit }: { limit?: number }) {
  const { dict } = useI18n();
  return (
    <ul className="why-list">
      {dict.home.why.slice(0, limit).map(([title, text]) => (
        <li key={title}>
          <strong>{title}</strong>
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * "Bald verfügbar": features that wait for data. Each item hides itself once it is
 * live: the scores and tips when the model leaves the live-only stage; the weather
 * forecast is removed from the texts when that model ships.
 */
export function Soon({ stage }: { stage: Stage | null }) {
  const { dict } = useI18n();
  const items = [
    ...(stage === "live_only" ? [dict.about.soon.scores] : []),
    dict.about.soon.weather,
  ];
  return (
    <section className="soon">
      <h2>{dict.about.soonTitle}</h2>
      <ul className="why-list soon-list">
        {items.map(([title, text]) => (
          <li key={title}>
            <strong>{title}</strong>
            <span>{text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "Was AnschlussRadar nicht tut": on the About page and at the top of the privacy page. */
export function NotList() {
  const { dict } = useI18n();
  return (
    <section className="not-list">
      <h2>{dict.about.notTitle}</h2>
      <ul>
        {dict.about.not.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

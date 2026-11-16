// "Was AnschlussRadar anders macht": three points, used on the start page and the About page.
import { useI18n } from "../i18n";

export function WhyList() {
  const { dict } = useI18n();
  return (
    <ul className="why-list">
      {dict.home.why.map(([title, text]) => (
        <li key={title}>
          <strong>{title}</strong>
          <span>{text}</span>
        </li>
      ))}
    </ul>
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

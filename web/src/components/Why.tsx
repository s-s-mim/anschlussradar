// "Was AnschlussRadar anders macht": three points, used on the start page and the About page.
import { useI18n } from "../i18n";
import { de } from "../i18n/de";
import { en } from "../i18n/en";

export function WhyList() {
  const { lang } = useI18n();
  const items = (lang === "de" ? de : en).home.why;
  return (
    <ul className="why-list">
      {items.map(([title, text]) => (
        <li key={title}>
          <strong>{title}</strong>
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}

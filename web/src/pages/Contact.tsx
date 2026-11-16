// Contact by e-mail only. A form would need an e-mail service and more text in the
// privacy policy; for a portfolio project a plain address is enough.
// (The API still has POST /contact, unused for now.)
import { useI18n } from "../i18n";
import { Link } from "../lib/router";
import { SITE, isPlaceholder } from "../site";

export function Contact() {
  const { t } = useI18n();
  return (
    <div className="page wrap narrow">
      <h1>{t("contact.title")}</h1>
      <p className="lead">{t("contact.lead")}</p>
      <p className="contact-mail">
        {isPlaceholder(SITE.email) ? (
          <mark>{SITE.email}</mark>
        ) : (
          <a href={`mailto:${SITE.email}?subject=AnschlussRadar`}>{SITE.email}</a>
        )}
      </p>
      <p className="small muted">
        {t("contact.privacyNote")} <Link href="/datenschutz">{t("nav.privacy")}</Link>
      </p>
      <p className="small muted">
        {t("contact.code")}{" "}
        <a href={SITE.sourceCode} target="_blank" rel="noopener noreferrer">
          GitHub
        </a>
      </p>
    </div>
  );
}

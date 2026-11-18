// Contact by e-mail only. A form would need an e-mail service and more text in the
// privacy policy; for a portfolio project a plain address is enough.
// (The API still has POST /contact, unused for now.)
import { useI18n } from "../i18n";
import { Link } from "../lib/router";
import { SITE, siteEmail } from "../site";

/** A plain person outline: marks the link as "about the author" without using a brand logo. */
export function PersonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Contact() {
  const { t } = useI18n();
  return (
    <div className="page wrap narrow">
      <h1>{t("contact.title")}</h1>
      <p className="lead">{t("contact.lead")}</p>
      <p className="contact-mail">
        <a href={`mailto:${siteEmail()}?subject=AnschlussRadar`}>{siteEmail()}</a>
      </p>
      <p>
        {t("contact.about")}{" "}
        <a className="profile-link" href={SITE.linkedin} target="_blank" rel="noopener noreferrer">
          <PersonIcon />
          LinkedIn
        </a>
      </p>
      <p className="small muted">
        {t("contact.privacyNote")} <Link href="/datenschutz">{t("nav.privacy")}</Link>
      </p>
      {SITE.sourcePublic && (
        <p className="small muted">
          {t("contact.code")}{" "}
          <a href={SITE.sourceCode} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </p>
      )}
    </div>
  );
}

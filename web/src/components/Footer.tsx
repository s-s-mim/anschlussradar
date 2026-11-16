import { useI18n } from "../i18n";
import { Link } from "../lib/router";
import { SITE } from "../site";

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="site-footer">
      <div className="wrap">
        <nav className="footer-links" aria-label="Footer">
          <Link href="/stations">{t("nav.stations")}</Link>
          <Link href="/map">{t("nav.map")}</Link>
          <Link href="/lines">{t("nav.lines")}</Link>
          <Link href="/help">{t("nav.help")}</Link>
          <Link href="/about">{t("nav.about")}</Link>
          <Link href="/contact">{t("nav.contact")}</Link>
          <Link href="/impressum">{t("nav.imprint")}</Link>
          <Link href="/datenschutz">{t("nav.privacy")}</Link>
        </nav>
        <p>
          <a href="https://transitous.org/sources/" target="_blank" rel="noopener noreferrer">
            {t("footer.planner")}
          </a>
          . {t("footer.notDb")}
        </p>
        <p>© 2026 {SITE.operatorName}</p>
      </div>
    </footer>
  );
}

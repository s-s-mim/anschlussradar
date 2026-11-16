import { LANGUAGES, useI18n } from "../i18n";
import type { Lang } from "../i18n";
import { Link } from "../lib/router";
import { LogoMark } from "./Logo";

export function Header({ path }: { path: string }) {
  const { t, lang, setLang } = useI18n();
  return (
    <header className="site-header">
      <a className="skip" href="#main">
        {t("nav.skip")}
      </a>
      <div className="wrap header-row">
        <Link href="/" className="brand" aria-label="AnschlussRadar">
          <LogoMark />
          <span>AnschlussRadar</span>
        </Link>
        <nav className="header-nav" aria-label={t("nav.search")}>
          <Link href="/help" aria-current={path === "/help" ? "page" : undefined}>
            {t("nav.help")}
          </Link>
          {/* A native menu: works with screen readers and opens the phone's own picker. */}
          <label className="lang">
            <span className="lang-code" aria-hidden="true">
              {lang.toUpperCase()}
            </span>
            <select value={lang} aria-label={t("nav.language")} onChange={(e) => setLang(e.target.value as Lang)}>
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} lang={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
        </nav>
      </div>
    </header>
  );
}

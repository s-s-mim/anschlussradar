import { useI18n } from "../i18n";
import type { Lang } from "../i18n";
import { Link } from "../lib/router";
import { LogoMark } from "./Logo";

export function Header({ path }: { path: string }) {
  const { t, lang, setLang } = useI18n();
  const other: Lang = lang === "de" ? "en" : "de";
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
          <button
            type="button"
            className="lang"
            onClick={() => setLang(other)}
            aria-label={`${t("nav.language")}: ${other === "de" ? "Deutsch" : "English"}`}
          >
            <span aria-hidden="true" className={lang === "de" ? "on" : ""}>DE</span>
            <span aria-hidden="true" className={lang === "en" ? "on" : ""}>EN</span>
          </button>
        </nav>
      </div>
    </header>
  );
}

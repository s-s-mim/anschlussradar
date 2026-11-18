import { useI18n } from "../i18n";
import { Link } from "../lib/router";
import { LanguageMenu } from "./LanguageMenu";
import { LogoMark } from "./Logo";
import { NavLinks } from "./TabBar";

export function Header({ path }: { path: string }) {
  const { t } = useI18n();
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
        <div className="header-nav">
          <NavLinks path={path} className="top-links" />
          <LanguageMenu />
        </div>
      </div>
    </header>
  );
}

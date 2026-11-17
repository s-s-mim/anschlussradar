// Main navigation: a tab bar at the bottom on phones (one tap back to the search
// from anywhere), the same links in the header on wider screens.
import { useI18n } from "../i18n";
import { Link } from "../lib/router";

const TABS = [
  { href: "/", key: "nav.search", match: ["/", "/connections"], icon: "M10.5 4a6.5 6.5 0 1 0 4 11.6l4.4 4.4 1.4-1.4-4.4-4.4A6.5 6.5 0 0 0 10.5 4Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z" },
  { href: "/map", key: "nav.map", match: ["/map", "/stations", "/station"], icon: "M6 4a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Zm12 4a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM9 15a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Zm-1.6-6.8 1.2 6.6m1.2.4 6.4-4.4M8.3 6.9l7.4 2.4" },
  { href: "/lines", key: "nav.lines", match: ["/lines", "/line"], icon: "M5 4v16M5 7h9a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h10" },
  { href: "/help", key: "nav.help", match: ["/help"], icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-2.6 6.6a2.6 2.6 0 1 1 3.8 2.3c-.8.4-1.2 1-1.2 1.8v.5M12 17.2v.3" },
];

export function NavLinks({ path, className }: { path: string; className: string }) {
  const { t } = useI18n();
  return (
    <nav className={className} aria-label={t("nav.main")}>
      {TABS.map((tab) => {
        const active = tab.match.includes(path);
        const filled = tab.href === "/";
        return (
          <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined}>
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path
                d={tab.icon}
                fill={filled ? "currentColor" : "none"}
                fillRule="evenodd"
                stroke={filled ? "none" : "currentColor"}
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>{t(tab.key)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

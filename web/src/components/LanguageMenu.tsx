// Compact language menu. The phone's own picker for <select> covers the whole screen
// on Android, so this is a small list under the button instead. Keyboard: arrows move,
// Enter picks, Escape closes; the list closes when you tap outside it.
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { LANGUAGES, useI18n } from "../i18n";
import type { Lang } from "../i18n";

export function LanguageMenu() {
  const { t, lang, setLang } = useI18n();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    // Focus the current language, so arrow keys start from there.
    list.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const pick = (code: Lang) => {
    setLang(code);
    setOpen(false);
  };

  const keys = (e: KeyboardEvent<HTMLUListElement>) => {
    const items = [...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") items[Math.min(i + 1, items.length - 1)]?.focus();
    else if (e.key === "ArrowUp") items[Math.max(i - 1, 0)]?.focus();
    else if (e.key === "Escape") setOpen(false);
    else return;
    e.preventDefault();
  };

  return (
    <div className="lang" ref={box}>
      <button
        type="button"
        className="lang-button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t("nav.language")}
        onClick={() => setOpen((o) => !o)}
      >
        {lang.toUpperCase()}
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      </button>
      {open && (
        <ul className="lang-list" ref={list} role="radiogroup" aria-label={t("nav.language")} onKeyDown={keys}>
          {LANGUAGES.map((l) => (
            <li key={l.code}>
              <button type="button" role="radio" aria-checked={l.code === lang} lang={l.code} onClick={() => pick(l.code)}>
                {l.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

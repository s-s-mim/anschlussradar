// "Jeden Tag prüfen": watch one connection and get a push only when a change is at risk.
import { useState } from "react";
import { useI18n } from "../i18n";
import { addWatch, PushError } from "../lib/push";
import type { Station } from "../lib/types";

/** Weekday names in the current language, Monday first (ISO 1..7). */
export function weekdayNames(lang: string): string[] {
  const monday = new Date(Date.UTC(2026, 10, 16)); // a Monday
  const fmt = new Intl.DateTimeFormat(lang, { weekday: "short", timeZone: "UTC" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(monday.getTime() + i * 86400000)));
}

export function WatchPanel({ from, to, departure }: { from: Station; to: Station; departure: string }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState("12345");
  const [state, setState] = useState<"idle" | "saving" | "saved" | PushError["reason"]>("idle");
  const names = weekdayNames(lang);

  if (!open) {
    return (
      <button type="button" className="ghost watch-open" onClick={() => setOpen(true)}>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        </svg>
        {t("watch.button")}
      </button>
    );
  }

  const toggle = (d: string) =>
    setDays((cur) => (cur.includes(d) ? cur.replace(d, "") : [...cur, d].sort().join("")));

  const save = async () => {
    setState("saving");
    try {
      await addWatch(from, to, departure, days, lang);
      setState("saved");
    } catch (e) {
      setState(e instanceof PushError ? e.reason : "unavailable");
    }
  };

  return (
    <div className="watch-panel">
      <p className="small">{t("watch.lead")}</p>
      <fieldset>
        <legend className="small muted">{t("watch.days")}</legend>
        <div className="days">
          {names.map((n, i) => {
            const d = String(i + 1);
            return (
              <label key={d} className={days.includes(d) ? "day on" : "day"}>
                <input type="checkbox" checked={days.includes(d)} onChange={() => toggle(d)} />
                {n}
              </label>
            );
          })}
        </div>
      </fieldset>
      {state === "saved" ? (
        <p className="notice ok" role="status">
          {t("watch.saved")}
        </p>
      ) : (
        <button type="button" className="primary" disabled={!days || state === "saving"} onClick={save}>
          {state === "saving" ? t("watch.saving") : `${t("watch.on")} (${departure})`}
        </button>
      )}
      {["denied", "unsupported", "unavailable", "tooMany"].includes(state) && (
        <p className="error-text" role="alert">
          {t(`watch.${state}`)}
        </p>
      )}
    </div>
  );
}

// The start page list of watched connections, read from the server for this device.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { existingDevice, listWatches, removeAllWatches, removeWatch } from "../lib/push";
import type { WatchView } from "../lib/push";
import { weekdayNames } from "./Watch";

export function WatchedList() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState<WatchView[]>([]);
  const names = weekdayNames(lang);

  useEffect(() => {
    if (!existingDevice()) return;
    listWatches()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (!items.length) return null;
  return (
    <section className="routes watched">
      <h2>{t("watch.title")}</h2>
      <ul>
        {items.map((w) => (
          <li key={w.id}>
            <span className="route-link">
              <strong>{w.departure}</strong> {w.from.name} <span aria-hidden="true">→</span> {w.to.name}
              <small className="muted"> {w.weekdays.split("").map((d) => names[Number(d) - 1]).join(", ")}</small>
            </span>
            <button
              type="button"
              className="remove"
              aria-label={`${t("watch.remove")}: ${w.from.name} – ${w.to.name}`}
              title={t("watch.remove")}
              onClick={() => removeWatch(w.id).then(() => setItems((cur) => cur.filter((x) => x.id !== w.id)))}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="link-button small" onClick={() => removeAllWatches().then(() => setItems([]))}>
        {t("watch.offAll")}
      </button>
    </section>
  );
}

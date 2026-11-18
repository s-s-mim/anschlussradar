// "Mein Standort" and "In der Nähe" under the From field.
// The phone asks for the position only after a tap and rounds it to about 100 m.
// "Mein Standort" plans from that point, so the trip starts with the walk to the stop;
// "In der Nähe" lists stations (or, with bus/tram ticked, stops of every kind).
// The position travels only in request bodies, never in a web address, and is not stored.
import { useState } from "react";
import { useI18n } from "../i18n";
import { nearbyStations } from "../lib/api";
import { PlaceIcon } from "./StationInput";
import type { NearbyStation, Station } from "../lib/types";

type State = "idle" | "locating" | "denied" | "failed" | "none" | "list";

function position(): Promise<{ lat: number; lon: number }> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject(new Error("unsupported"));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: Math.round(p.coords.latitude * 1000) / 1000, lon: Math.round(p.coords.longitude * 1000) / 1000 }),
      (e) => reject(e),
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 120000 },
    );
  });
}

const PIN = "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Zm0 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Z";

export function NearMe({ onPick, all }: { onPick: (s: Station) => void; all: boolean }) {
  const { t, lang } = useI18n();
  const [state, setState] = useState<State>("idle");
  const [items, setItems] = useState<NearbyStation[]>([]);

  const find = async (mode: "mine" | "list") => {
    setState("locating");
    let pos;
    try {
      pos = await position();
    } catch (e) {
      setState((e as GeolocationPositionError)?.code === 1 ? "denied" : "failed");
      return;
    }
    if (mode === "mine") {
      // The search starts at the position itself, so the planner adds the walk to the
      // best stop. The position stays in this tab; the address bar only says "here" (lib/query.ts).
      const me: Station = { id: "here", kind: "here", name: t("near.mine"), lat: pos.lat, lon: pos.lon };
      onPick(me);
      setState("idle");
      return;
    }
    try {
      const found = await nearbyStations(pos.lat, pos.lon, all);
      if (found.length === 0) return setState("none");
      setItems(found);
      setState("list");
    } catch {
      setState("failed");
    }
  };

  const metres = (m: number) =>
    m < 1000 ? `${m} m` : `${(m / 1000).toLocaleString(lang, { maximumFractionDigits: 1 })} km`;

  return (
    <div className="near-me">
      <div className="near-buttons">
        <button type="button" className="chip" onClick={() => find("mine")} disabled={state === "locating"}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d={PIN} fill="currentColor" fillRule="evenodd" />
          </svg>
          {t("near.mine")}
        </button>
        <button type="button" className="chip" onClick={() => find("list")} disabled={state === "locating"}>
          {t(all ? "near.listAll" : "near.list")}
        </button>
      </div>
      {state === "locating" && (
        <p className="small muted" role="status">
          {t("near.locating")}
        </p>
      )}
      {state === "denied" && <p className="small error-text">{t("near.denied")}</p>}
      {state === "failed" && <p className="small error-text">{t("near.failed")}</p>}
      {state === "none" && <p className="small muted">{t(all ? "near.noneAll" : "near.none")}</p>}
      {state === "list" && (
        <ul className="near-list">
          {items.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(s);
                  setState("idle");
                }}
              >
                <PlaceIcon kind={s.kind} />
                <span className="place-text">{s.name}</span>
                <span className="muted small">{metres(s.distanceM)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

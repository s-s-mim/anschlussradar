// The search lives in the address bar, so results can be reloaded, shared and
// reached with the back button: /connections?from=50.084,8.469&fromName=Kriftel&...
import type { Station } from "./types";

export interface Search {
  from: Station;
  to: Station;
  date: string; // yyyy-mm-dd, German time
  time: string; // HH:MM
  arriveBy: boolean;
}

export const place = (s: Station) => `${s.lat.toFixed(5)},${s.lon.toFixed(5)}`;

function station(value: string | null, name: string | null): Station | null {
  if (!value || !name) return null;
  const [lat, lon] = value.split(",").map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return { id: value, name, lat, lon };
}

export function toParams(s: Search): string {
  const p = new URLSearchParams({
    from: place(s.from),
    fromName: s.from.name,
    to: place(s.to),
    toName: s.to.name,
    date: s.date,
    time: s.time,
  });
  if (s.arriveBy) p.set("arrive", "1");
  return p.toString();
}

export function fromParams(p: URLSearchParams): Partial<Search> {
  const from = station(p.get("from"), p.get("fromName"));
  const to = station(p.get("to"), p.get("toName"));
  const date = p.get("date");
  const time = p.get("time");
  return {
    from: from ?? undefined,
    to: to ?? undefined,
    date: date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined,
    time: time && /^\d{2}:\d{2}$/.test(time) ? time : undefined,
    arriveBy: p.get("arrive") === "1",
  };
}

// The search lives in the address bar, so results can be reloaded, shared and
// reached with the back button: /connections?from=50.084,8.469&fromName=Kriftel&...
import type { Station } from "./types";

export interface Search {
  from: Station;
  to: Station;
  date: string; // yyyy-mm-dd, German time
  time: string; // HH:MM
  arriveBy: boolean;
  /** Also buses, trams and underground lines, not only trains. */
  local: boolean;
}

export const place = (s: Station) => `${s.lat.toFixed(5)},${s.lon.toFixed(5)}`;

/** Private places stay out of the address bar: "Mein Standort" and typed addresses
 * (which may be someone's home). Their coordinates stay in this tab
 * (sessionStorage); the address bar only says "here" or "address". A shared link
 * then carries no one's position. Stations and stops are public and stay in it. */
type Side = "from" | "to";
const KEY = (side: Side) => `ar.place.${side}`;
const isPrivate = (s: Station) => s.kind === "here" || s.kind === "address";

function remember(side: Side, s: Station): void {
  try {
    sessionStorage.setItem(KEY(side), JSON.stringify({ lat: s.lat, lon: s.lon, name: s.name, detail: s.detail }));
  } catch {
    // private mode without storage: the search still works until a reload
  }
}

function recall(side: Side, kind: "here" | "address", name: string | null): Station | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY(side)) ?? "null");
    if (v && Number.isFinite(v.lat) && Number.isFinite(v.lon)) {
      return { id: kind, kind, name: name ?? v.name ?? "", detail: v.detail, lat: v.lat, lon: v.lon };
    }
  } catch {
    // nothing stored
  }
  return null;
}

function urlPlace(side: Side, s: Station): string {
  if (!isPrivate(s)) return place(s);
  remember(side, s);
  return s.kind === "here" ? "here" : "address";
}

function station(side: Side, value: string | null, name: string | null): Station | null {
  if (value === "here" || value === "address") return recall(side, value, value === "here" ? name : null);
  if (!value || !name) return null;
  const [lat, lon] = value.split(",").map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return { id: value, name, lat, lon };
}

export function toParams(s: Search): string {
  const p = new URLSearchParams({ from: urlPlace("from", s.from) });
  // An address's name is the address itself, so it stays in the tab too.
  if (s.from.kind !== "address") p.set("fromName", s.from.name);
  p.set("to", urlPlace("to", s.to));
  if (s.to.kind !== "address") p.set("toName", s.to.name);
  p.set("date", s.date);
  p.set("time", s.time);
  if (s.arriveBy) p.set("arrive", "1");
  if (s.local) p.set("local", "1");
  return p.toString();
}

export function fromParams(p: URLSearchParams): Partial<Search> {
  const from = station("from", p.get("from"), p.get("fromName"));
  const to = station("to", p.get("to"), p.get("toName"));
  const date = p.get("date");
  const time = p.get("time");
  return {
    from: from ?? undefined,
    to: to ?? undefined,
    date: date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined,
    time: time && /^\d{2}:\d{2}$/.test(time) ? time : undefined,
    arriveBy: p.get("arrive") === "1",
    local: p.has("local") ? p.get("local") === "1" : undefined,
  };
}

// Everything the app remembers stays in this browser (localStorage). Nothing is
// sent to the server. Every access is wrapped, because private windows and some
// settings block storage; the app still works then, it just forgets.

import type { Station } from "./types";

const KEYS = {
  lang: "ar.lang",
  saved: "ar.savedRoutes",
  recent: "ar.recentRoutes",
} as const;

export interface Route {
  from: Station;
  to: Station;
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked or full: nothing to do
  }
}

const same = (a: Route, b: Route) => a.from.id === b.from.id && a.to.id === b.to.id;

export const store = {
  lang: () => read<string | null>(KEYS.lang, null),
  setLang: (lang: string) => write(KEYS.lang, lang),

  saved: () => read<Route[]>(KEYS.saved, []),
  isSaved: (r: Route) => store.saved().some((s) => same(s, r)),
  toggleSaved(r: Route): boolean {
    const list = store.saved();
    const exists = list.some((s) => same(s, r));
    write(KEYS.saved, exists ? list.filter((s) => !same(s, r)) : [r, ...list].slice(0, 12));
    return !exists;
  },

  recent: () => read<Route[]>(KEYS.recent, []),
  addRecent(r: Route): void {
    write(KEYS.recent, [r, ...store.recent().filter((s) => !same(s, r))].slice(0, 5));
  },

  clearAll(): void {
    try {
      Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
      sessionStorage.clear();
    } catch {
      // nothing stored
    }
  },
};

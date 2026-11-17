// Everything the app remembers stays in this browser (localStorage). Nothing is
// sent to the server. Every access is wrapped, because private windows and some
// settings block storage; the app still works then, it just forgets.

import type { Station } from "./types";

const KEYS = {
  lang: "ar.lang",
  saved: "ar.savedRoutes",
  recent: "ar.recentRoutes",
  searched: "ar.searched",
  answered: "ar.answered",
  local: "ar.local",
  questions: "ar.questions",
} as const;

export interface MyQuestion {
  id: string;
  text: string;
  sent: string; // ISO time
}

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
    write(KEYS.searched, true);
  },

  /** Transfers already answered with "Hat's geklappt?", so the question is not asked twice. */
  isAnswered: (key: string) => read<string[]>(KEYS.answered, []).includes(key),
  markAnswered(key: string): void {
    write(KEYS.answered, [key, ...read<string[]>(KEYS.answered, [])].slice(0, 50));
  },

  /** The last choice for "also buses, trams and underground", used as the default. */
  local: () => read<boolean>(KEYS.local, false),
  setLocal: (on: boolean) => write(KEYS.local, on),

  /** Questions sent from the help page. Only the random ID and the text, on this phone. */
  questions: () => read<MyQuestion[]>(KEYS.questions, []),
  addQuestion(q: MyQuestion): void {
    write(KEYS.questions, [q, ...store.questions().filter((x) => x.id !== q.id)].slice(0, 20));
  },
  removeQuestion(id: string): void {
    write(KEYS.questions, store.questions().filter((x) => x.id !== id));
  },

  /** After the first search the start page shows a short link instead of the intro. */
  hasSearched: () => read<boolean>(KEYS.searched, false),

  clearAll(): void {
    try {
      Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
      sessionStorage.clear();
    } catch {
      // nothing stored
    }
  },
};

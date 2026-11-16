import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { store } from "../lib/storage";
import { de } from "./de";
import { en } from "./en";

export type Lang = "de" | "en";
const DICTS = { de, en };

type Vars = Record<string, string | number>;
export type T = (key: string, vars?: Vars) => string;

function lookup(dict: unknown, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split(".")) {
    if (node && typeof node === "object" && part in node) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return typeof node === "string" ? node : undefined;
}

function initialLang(): Lang {
  const saved = store.lang();
  if (saved === "de" || saved === "en") return saved;
  const browser = typeof navigator !== "undefined" ? navigator.language : "de";
  return browser.toLowerCase().startsWith("en") ? "en" : "de";
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: T;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    store.setLang(next);
    setLangState(next);
  }, []);

  const t = useCallback<T>(
    (key, vars) => {
      const dict = DICTS[lang];
      let k = key;
      if (vars && typeof vars.count === "number") {
        const form = new Intl.PluralRules(lang).select(vars.count);
        if (lookup(dict, `${key}_${form}`)) k = `${key}_${form}`;
        else if (lookup(dict, `${key}_other`)) k = `${key}_other`;
      }
      const text = lookup(dict, k) ?? lookup(de, k) ?? key;
      return vars ? text.replace(/\{(\w+)\}/g, (m, name: string) => String(vars[name] ?? m)) : text;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { store } from "../lib/storage";
import { am } from "./am";
import { ar } from "./ar";
import { bn } from "./bn";
import { de } from "./de";
import type { Dict } from "./de";
import { en } from "./en";
import { hi } from "./hi";
import { mk } from "./mk";
import { pl } from "./pl";
import { ro } from "./ro";
import { ru } from "./ru";
import { tr } from "./tr";
import { uk } from "./uk";
import { ur } from "./ur";

export type Lang =
  | "de"
  | "en"
  | "tr"
  | "uk"
  | "pl"
  | "ru"
  | "ro"
  | "mk"
  | "ar"
  | "ur"
  | "hi"
  | "bn"
  | "am";

/** In the order of the language menu; each name in its own language. */
export const LANGUAGES: { code: Lang; name: string; rtl?: boolean }[] = [
  { code: "de", name: "Deutsch" },
  { code: "en", name: "English" },
  { code: "tr", name: "Türkçe" },
  { code: "uk", name: "Українська" },
  { code: "pl", name: "Polski" },
  { code: "ru", name: "Русский" },
  { code: "ro", name: "Română" },
  { code: "mk", name: "Македонски" },
  { code: "ar", name: "العربية", rtl: true },
  { code: "ur", name: "اردو", rtl: true },
  { code: "hi", name: "हिन्दी" },
  { code: "bn", name: "বাংলা" },
  { code: "am", name: "አማርኛ" },
];

const DICTS: Record<Lang, Dict> = { de, en, tr, uk, pl, ru, ro, mk, ar, ur, hi, bn, am };
const isLang = (v: unknown): v is Lang => LANGUAGES.some((l) => l.code === v);

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
  // German first, whatever the phone's language: the app is about German trains and
  // most texts in the data are German. People pick another language in the menu,
  // and that choice is remembered.
  const saved = store.lang();
  return isLang(saved) ? saved : "de";
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: T;
  /** The whole text set, for pages that render lists (help, about). */
  dict: Dict;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = LANGUAGES.find((l) => l.code === lang)?.rtl ? "rtl" : "ltr";
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
      const text = lookup(dict, k) ?? lookup(en, k) ?? lookup(de, k) ?? key;
      return vars ? text.replace(/\{(\w+)\}/g, (m, name: string) => String(vars[name] ?? m)) : text;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t, dict: DICTS[lang] }), [lang, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}

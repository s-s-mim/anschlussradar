// DB reason codes as text, per language. de.json is DB's own wording; en.json is a
// reviewed translation. The other languages are generated from en.json with
// scripts/translate_messages.py (Azure OpenAI) and listed here once they exist.
// A missing language shows English, a missing code shows nothing.
import type { Lang } from "..";
import de from "./de.json";
import en from "./en.json";

type Texts = Record<string, string>;

const TEXTS: Partial<Record<Lang, Texts>> = { de, en };

export function messageText(lang: Lang, code: number): string | null {
  const key = String(code);
  return TEXTS[lang]?.[key] ?? TEXTS.en?.[key] ?? null;
}

/** Lower case without accents, umlauts spelled out, spaces and signs dropped:
 * "re30" finds "RE 30", "muenchen" and "munchen" find "München". */
export function normalizeText(s: string): string {
  return s
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/g, "");
}

/** Like normalizeText, but "muenchen" also matches "Munchen" typed without the e. */
export function matchesText(haystack: string, query: string): boolean {
  const q = normalizeText(query);
  if (!q) return true;
  const h = normalizeText(haystack);
  return h.includes(q) || h.replace(/(?<=[aou])e/g, "").includes(q.replace(/(?<=[aou])e/g, ""));
}

// Finds help entries that fit a question, on the phone, in the user's language.
// Word matching, not AI: nothing is sent anywhere.

export interface HelpEntry {
  q: string;
  a: string[];
  list?: string[];
}

function words(s: string): string[] {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // Latin accents only; other scripts keep their marks
    .split(/[^\p{L}\p{N}\p{M}]+/u)
    .filter((w) => w.length >= 3);
}

function hit(word: string, inText: string[]): number {
  let best = 0;
  for (const w of inText) {
    if (w === word) return 1;
    // "umstieg" finds "umstiege", "delay" finds "delays"
    const short = Math.min(w.length, word.length);
    if (short >= 4 && (w.startsWith(word.slice(0, short)) || word.startsWith(w.slice(0, short)))) best = 0.7;
  }
  return best;
}

export function searchHelp(query: string, entries: HelpEntry[], limit = 3): HelpEntry[] {
  const q = [...new Set(words(query))];
  if (q.length === 0) return [];
  const docs = entries.map((e) => ({
    e,
    title: words(e.q),
    body: words([...e.a, ...(e.list ?? [])].join(" ")),
  }));
  // Rare words count more: "was", "der", "the" appear everywhere and say little.
  const weight = (w: string) => {
    const df = docs.filter((d) => hit(w, d.title) > 0 || hit(w, d.body) > 0).length;
    // A word no entry contains counts fully: the help probably doesn't cover the question.
    return Math.log(1 + docs.length / Math.max(df, 1));
  };
  const weights = q.map(weight);
  const total = weights.reduce((a, b) => a + b, 0);
  return docs
    .map((d) => ({
      e: d.e,
      score: q.reduce((sum, w, i) => sum + weights[i] * Math.max(hit(w, d.title), 0.6 * hit(w, d.body)), 0) / total,
    }))
    .filter((s) => s.score >= 0.45)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((s) => s.e);
}

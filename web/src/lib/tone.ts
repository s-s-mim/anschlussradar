import type { LiveStatus, Transfer } from "./types";

export type Tone = "good" | "fair" | "risk" | "bad" | "none";

export function probabilityTone(p: number | null): Tone {
  if (p === null) return "none";
  if (p >= 0.9) return "good";
  if (p >= 0.75) return "fair";
  if (p >= 0.5) return "risk";
  return "bad";
}

const LIVE: Record<LiveStatus, Tone> = {
  ok: "good",
  tight: "fair",
  at_risk: "risk",
  missed: "bad",
  cancelled: "bad",
};

/** What a transfer looks like right now: live status first, then the learned chance. */
export function transferTone(t: Transfer): Tone {
  return t.liveStatus ? LIVE[t.liveStatus] : probabilityTone(t.probability);
}

export const pct = (p: number) => Math.round(p * 100);

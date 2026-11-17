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

/** Punctuality bands, the same on the network map and in the charts by hour.
 * Long-distance trains manage about two thirds, regional trains about nine in ten. */
export type Band = "good" | "fair" | "risk" | "bad" | "none";
export const BANDS: Band[] = ["good", "fair", "risk", "bad", "none"];
export function punctualityBand(onTime: number | null): Band {
  if (onTime === null) return "none";
  if (onTime >= 0.9) return "good";
  if (onTime >= 0.8) return "fair";
  if (onTime >= 0.65) return "risk";
  return "bad";
}

export const pct = (p: number) => Math.round(p * 100);

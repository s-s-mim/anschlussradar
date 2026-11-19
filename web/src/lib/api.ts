import type { ApiErrorBody, Board, Hub, JourneysResponse, LineDetail, LineSummary, ModelStatus, NearbyStation, NetworkStation, Station } from "./types";

const BASE = (import.meta.env.VITE_API_BASE || "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly field?: string,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "offline", "network");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    throw new ApiError(res.status, err?.code ?? "unknown", err?.message ?? res.statusText, err?.field);
  }
  return body as T;
}

/** Stations, and stops and addresses when needed. POST, so a typed address stays out of URLs.
 * Two steps: "local" answers at once from the app's own station list and says whether
 * more is worth asking for; "more" then brings the stops and addresses from Transitous. */
export function searchPlaces(
  text: string,
  lang: string,
  all: boolean,
  step: "local" | "more",
  signal?: AbortSignal,
): Promise<{ places: Station[]; more?: boolean }> {
  return request<{ places: Station[]; more?: boolean }>("/places", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang, all, step }),
    signal,
  });
}

/** Wakes the API when the app opens, so the first search does not wait for a cold start. */
export function warmUp(): void {
  fetch(`${BASE}/warm`).catch(() => undefined);
}

export interface JourneyQuery {
  from: string;
  to: string;
  time: string; // ISO with offset
  arriveBy: boolean;
  local: boolean;
}

export function findJourneys(q: JourneyQuery, signal?: AbortSignal): Promise<JourneysResponse> {
  // POST: a position or an address never ends up in a URL or a request log.
  return request<JourneysResponse>("/journeys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from: q.from, to: q.to, time: q.time, arriveBy: String(q.arriveBy), rail: String(!q.local) }),
    signal,
  });
}

export function getModelStatus(): Promise<ModelStatus> {
  return request<ModelStatus>("/model/status");
}

export interface FeedbackBody {
  station: string;
  inTrain: string;
  outTrain: string;
  plannedArrival: string;
  plannedDeparture: string;
  made: boolean;
}

/** "Hat's geklappt?": the answer and the transfer it belongs to, nothing else. */
export function sendFeedback(body: FeedbackBody): Promise<{ status: string }> {
  return request("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getHubs(): Promise<Hub[]> {
  return request<{ stations: Hub[] }>("/hubs").then((b) => b.stations);
}

export function getNetwork(): Promise<{ available: boolean; stations: NetworkStation[] }> {
  return request<{ available: boolean; stations: NetworkStation[] }>("/network");
}

export function getLines(): Promise<{ available: boolean; lines: LineSummary[] }> {
  return request<{ available: boolean; lines: LineSummary[] }>("/lines");
}

export function getLine(id: string, signal?: AbortSignal): Promise<LineDetail> {
  return request<LineDetail>(`/lines/${encodeURIComponent(id)}`, { signal });
}

export function getBoard(eva: number, signal?: AbortSignal): Promise<Board> {
  return request<Board>(`/hubs/${eva}/board`, { signal });
}

export interface QuestionView {
  id: string;
  text: string;
  answer: string | null;
  answeredAt: string | null;
}

export function sendQuestion(
  text: string,
  lang: string,
  subscription?: PushSubscriptionJSON,
): Promise<{ question: QuestionView; notify: boolean }> {
  return request("/questions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang, subscription }),
  });
}

export function getQuestion(id: string): Promise<QuestionView> {
  return request<{ question: QuestionView }>(`/questions/${encodeURIComponent(id)}`).then((r) => r.question);
}

/** The AI step. available=false while it is switched off; answer=null when it doesn't know. */
export function ask(text: string, lang: string): Promise<{ available: boolean; answer: string | null }> {
  return request("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang }),
  });
}

/** Stations near a position. The position goes in the body, never in the address. */
export function nearbyStations(lat: number, lon: number, all: boolean): Promise<NearbyStation[]> {
  return request<{ stations: NearbyStation[] }>("/stations/nearby", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon, all }),
  }).then((r) => r.stations);
}


import type { ApiErrorBody, JourneysResponse, ModelStatus, Station } from "./types";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export function searchStations(q: string, signal?: AbortSignal): Promise<Station[]> {
  const params = new URLSearchParams({ q, limit: "8" });
  return request<{ stations: Station[] }>(`/stations?${params}`, { signal }).then((b) => b.stations);
}

export interface JourneyQuery {
  from: string;
  to: string;
  time: string; // ISO with offset
  arriveBy: boolean;
}

export function findJourneys(q: JourneyQuery, signal?: AbortSignal): Promise<JourneysResponse> {
  const params = new URLSearchParams({
    from: q.from,
    to: q.to,
    time: q.time,
    arriveBy: String(q.arriveBy),
  });
  return request<JourneysResponse>(`/journeys?${params}`, { signal });
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

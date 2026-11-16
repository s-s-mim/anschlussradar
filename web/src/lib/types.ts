// Shapes of the API answers (see src/anschlussradar/api in the Python code).

export type Stage = "live_only" | "early" | "full";
export type LiveStatus = "ok" | "tight" | "at_risk" | "missed" | "cancelled";
export type Confidence = "limited" | "medium" | "high";

export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
}

export interface Leg {
  mode: string;
  line: string | null;
  category: string | null;
  number: string | null;
  headsign: string | null;
  from: string | null;
  to: string | null;
  departurePlanned: string | null;
  departure: string | null;
  arrivalPlanned: string | null;
  arrival: string | null;
  departureDelay: number | null;
  arrivalDelay: number | null;
  departureTrack: string | null;
  departureTrackPlanned: string | null;
  arrivalTrack: string | null;
  arrivalTrackPlanned: string | null;
  realTime: boolean;
  cancelled: boolean;
  /** DB reason codes at recorded hubs: why the train is late, what is missing on board. */
  messages: { code: number; kind: "delay" | "quality" }[];
}

export interface Transfer {
  station: string | null;
  plannedBufferMinutes: number | null;
  arrivalTrack: string | null;
  departureTrack: string | null;
  probability: number | null;
  confidence: Confidence | null;
  observations: number;
  earlyEstimate: boolean;
  liveStatus: LiveStatus | null;
  liveSlackMinutes: number | null;
  recordedHub: boolean;
  note: "cancelled" | "not_rail" | null;
}

export interface Journey {
  departure: string | null;
  arrival: string | null;
  durationMinutes: number;
  transfersCount: number;
  reliability: number | null;
  legs: Leg[];
  transfers: Transfer[];
}

export interface JourneysResponse {
  stage: Stage;
  showBanner: boolean;
  journeys: Journey[];
  attribution: string;
}

export interface ModelStatus {
  stage: Stage;
  show_banner: boolean;
  weeks_of_data: number | null;
}

export interface ApiErrorBody {
  error: { code: string; message: string; field?: string };
}

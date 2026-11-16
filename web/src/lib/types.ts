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
  messages: TrainNote[];
  /** Station group number when the stop is a recorded hub (it then has a station page). */
  fromHub: number | null;
  toHub: number | null;
  /** Typical departure delay at a recorded hub over the last 4 weeks. */
  forecast: { typical: number; high: number; lateShare: number; trips: number } | null;
}

export interface TrainNote {
  code: number;
  kind: "delay" | "quality";
}

export interface Hub {
  eva: number;
  name: string;
  state: string;
}

export interface BoardDeparture {
  category: string | null;
  number: string | null;
  line: string | null;
  destination: string | null;
  departurePlanned: string | null;
  departure: string | null;
  delay: number | null;
  platform: string | null;
  platformPlanned: string | null;
  cancelled: boolean;
  messages: TrainNote[];
}

export interface HourStat {
  hour: number;
  departures: number;
  onTime: number | null;
  cancelled: number;
}

export interface Board {
  eva: number;
  name: string;
  available: boolean;
  departures: BoardDeparture[];
  hourly: HourStat[];
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

export interface Tip {
  kind: "earlier" | "transfer";
  departure: string | null;
  departureIso: string | null;
  arrival: string | null;
  reliability: number;
  previous: number;
  minutes?: number;
  station?: string | null;
}

export interface Journey {
  departure: string | null;
  arrival: string | null;
  durationMinutes: number;
  transfersCount: number;
  reliability: number | null;
  legs: Leg[];
  transfers: Transfer[];
  tips: Tip[];
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

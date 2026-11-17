// Push alerts for watched connections. The phone gets a random device ID; the server
// stores it with the push address the browser hands out, nothing else about the person.
import { ApiError, request } from "./api";
import type { Station } from "./types";

const DEVICE_KEY = "ar.device";

export interface WatchView {
  id: string;
  from: { name: string; place: string };
  to: { name: string; place: string };
  departure: string;
  weekdays: string;
  local: boolean;
}

export function existingDevice(): string | null {
  try {
    return localStorage.getItem(DEVICE_KEY);
  } catch {
    return null;
  }
}

function device(): string {
  let id = existingDevice();
  if (!id) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    try {
      localStorage.setItem(DEVICE_KEY, id);
    } catch {
      // storage blocked: the watch still works until the page is reloaded
    }
  }
  return id;
}

export function forgetDevice(): void {
  try {
    localStorage.removeItem(DEVICE_KEY);
  } catch {
    // nothing stored
  }
}

export const pushSupported = () =>
  "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/** The server's public key as the browser wants it: raw bytes in a plain ArrayBuffer. */
function keyBytes(base64url: string): ArrayBuffer {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes.buffer;
}

export class PushError extends Error {
  constructor(readonly reason: "unsupported" | "denied" | "unavailable" | "tooMany") {
    super(reason);
  }
}

export async function subscription(): Promise<PushSubscriptionJSON> {
  if (!pushSupported()) throw new PushError("unsupported");
  if ((await Notification.requestPermission()) !== "granted") throw new PushError("denied");
  let key: string;
  try {
    key = (await request<{ publicKey: string }>("/push/key")).publicKey;
  } catch {
    throw new PushError("unavailable");
  }
  const reg = await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }));
  return sub.toJSON();
}

export async function addWatch(
  from: Station,
  to: Station,
  departure: string,
  weekdays: string,
  lang: string,
  local: boolean,
): Promise<WatchView> {
  const sub = await subscription();
  const place = (s: Station) => `${s.lat.toFixed(5)},${s.lon.toFixed(5)}`;
  try {
    const res = await request<{ watch: WatchView }>("/watches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device: device(),
        subscription: sub,
        from: { name: from.name, place: place(from) },
        to: { name: to.name, place: place(to) },
        departure,
        weekdays,
        lang,
        local,
      }),
    });
    return res.watch;
  } catch (e) {
    throw new PushError(e instanceof ApiError && e.status === 409 ? "tooMany" : "unavailable");
  }
}

export async function listWatches(): Promise<WatchView[]> {
  const id = existingDevice();
  if (!id) return [];
  return request<{ watches: WatchView[] }>(`/watches/${id}`).then((r) => r.watches);
}

export async function removeWatch(watchId: string): Promise<void> {
  const id = existingDevice();
  if (id) await request(`/watches/${id}/${watchId}`, { method: "DELETE" });
}

/** Delete everything the server holds for this phone and unsubscribe from push. */
export async function removeAllWatches(): Promise<void> {
  const id = existingDevice();
  if (id) await request(`/watches/${id}`, { method: "DELETE" }).catch(() => undefined);
  forgetDevice();
  if (pushSupported()) {
    const reg = await navigator.serviceWorker.getRegistration();
    await (await reg?.pushManager.getSubscription())?.unsubscribe();
  }
}

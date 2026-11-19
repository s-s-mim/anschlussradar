// "Install as app": Chrome and Edge (Android, Windows, Mac) fire beforeinstallprompt
// when the app can be installed; we keep the event so a button can open the browser's
// own install dialog. Safari on iPhone has no such event, so the box shows the steps.
// This module is imported in main.tsx, so the event is caught even before any page renders.

interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((fn) => fn());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // we show our own box instead of the browser's mini bar
    deferred = e as InstallEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    notify();
  });
}

export const install = {
  /** Already running as an installed app. */
  installed: () =>
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true,
  canPrompt: () => deferred !== null,
  isIos: () =>
    /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
  async prompt(): Promise<boolean> {
    if (!deferred) return false;
    const e = deferred;
    deferred = null;
    await e.prompt();
    const { outcome } = await e.userChoice;
    notify();
    return outcome === "accepted";
  },
  subscribe(fn: () => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

// "Neue Version verfügbar – Neu laden": shown when a new release arrives while the
// app is open. The service worker takes over at once (skipWaiting), so the change of
// controller is the signal. A first install has no previous controller: no note then.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";

export function UpdateNote() {
  const { t } = useI18n();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const hadController = !!navigator.serviceWorker.controller;
    const onChange = () => {
      if (hadController) setReady(true);
    };
    navigator.serviceWorker.addEventListener("controllerchange", onChange);
    // Look for a new release when the app comes back to the front, and every 30 minutes.
    const check = () => navigator.serviceWorker.getRegistration().then((r) => r?.update()).catch(() => undefined);
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);
    const timer = window.setInterval(check, 30 * 60 * 1000);
    return () => {
      navigator.serviceWorker.removeEventListener("controllerchange", onChange);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(timer);
    };
  }, []);

  if (!ready) return null;
  return (
    <div className="update-note" role="status">
      <span>{t("update.available")}</span>
      <button type="button" onClick={() => window.location.reload()}>
        {t("update.reload")}
      </button>
    </div>
  );
}

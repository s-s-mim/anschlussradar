// Learning banner: shown while the model stage is not "full".
// It disappears on its own once the weekly retrain promotes a model that meets
// the full criteria; no frontend release is needed. Wired into the app in phase 4.

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type Stage = "live_only" | "early" | "full";

interface ModelStatus {
  stage: Stage;
  show_banner: boolean;
}

const CACHE_KEY = "ar.modelStatus";

function readCache(): ModelStatus | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as ModelStatus) : null;
  } catch {
    return null;
  }
}

export function LearningBanner() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<ModelStatus | null>(readCache);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/model/status")
      .then((r) => (r.ok ? (r.json() as Promise<ModelStatus>) : null))
      .then((s) => {
        if (cancelled || !s) return;
        setStatus(s);
        try {
          sessionStorage.setItem(CACHE_KEY, JSON.stringify(s));
        } catch {
          // storage blocked: the banner still works, it just fetches again next time
        }
      })
      .catch(() => {
        // offline: keep the cached status, or show nothing
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status || !status.show_banner) return null;

  return (
    <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      <p className="font-semibold">{t("banner.title")}</p>
      <p>{t(status.stage === "live_only" ? "banner.liveOnly" : "banner.early")}</p>
    </div>
  );
}

// Badge text next to a score: "early estimate" and the confidence label.
export function confidenceText(
  t: (key: string, opts?: Record<string, unknown>) => string,
  confidence: "limited" | "medium" | "high",
  observations: number,
  earlyEstimate: boolean,
): string {
  const parts: string[] = [];
  if (earlyEstimate) parts.push(t("score.earlyEstimate"));
  if (confidence === "limited") parts.push(t("score.limitedData"));
  if (confidence === "medium") parts.push(t("score.basedOn", { count: observations }));
  return parts.join(" · ");
}

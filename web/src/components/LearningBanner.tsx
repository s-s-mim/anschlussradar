// Shown while the model stage is not "full". It disappears by itself once the weekly
// retrain promotes a model that meets the full criteria; no web release is needed.
import { useI18n } from "../i18n";
import type { Stage } from "../lib/types";

export function LearningBanner({ stage }: { stage: Stage | null }) {
  const { t } = useI18n();
  if (!stage || stage === "full") return null;
  return (
    <div role="status" className="banner">
      <strong>{t("banner.title")}</strong> {t(`banner.${stage}`)}
    </div>
  );
}

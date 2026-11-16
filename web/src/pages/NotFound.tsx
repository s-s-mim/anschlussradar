import { useI18n } from "../i18n";
import { Link } from "../lib/router";

export function NotFound() {
  const { t } = useI18n();
  return (
    <div className="page wrap narrow">
      <h1>{t("notFound.title")}</h1>
      <p>
        <Link href="/">{t("notFound.back")}</Link>
      </p>
    </div>
  );
}

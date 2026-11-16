import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { getHubs } from "../lib/api";
import { Link } from "../lib/router";
import type { Hub } from "../lib/types";

export function Stations() {
  const { t } = useI18n();
  const [hubs, setHubs] = useState<Hub[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getHubs()
      .then(setHubs)
      .catch(() => setFailed(true));
  }, []);

  return (
    <div className="page wrap narrow">
      <h1>{t("board.hubsTitle")}</h1>
      <p className="lead">{t("board.hubsLead")}</p>
      {failed && <p className="notice error">{t("errors.generic")}</p>}
      {!hubs && !failed && (
        <div className="loading" role="status">
          <span />
          <span />
          <span />
        </div>
      )}
      {hubs && (
        <ul className="hub-list">
          {hubs.map((h) => (
            <li key={h.eva}>
              <Link href={`/station?eva=${h.eva}`}>{h.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

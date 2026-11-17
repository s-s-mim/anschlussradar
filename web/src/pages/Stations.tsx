import { useEffect, useState } from "react";
import { matchesText } from "../lib/text";
import { useI18n } from "../i18n";
import { getHubs } from "../lib/api";
import { Link } from "../lib/router";
import type { Hub } from "../lib/types";

export function Stations() {
  const { t } = useI18n();
  const [hubs, setHubs] = useState<Hub[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    getHubs()
      .then(setHubs)
      .catch(() => setFailed(true));
  }, []);

  return (
    <div className="page wrap narrow">
      <h1>{t("board.hubsTitle")}</h1>
      <p className="lead">{t("board.hubsLead")}</p>
      <p>
        <Link href="/map">{t("network.open")}</Link>
      </p>
      {failed && <p className="notice error">{t("errors.generic")}</p>}
      {!hubs && !failed && (
        <div className="loading" role="status">
          <span />
          <span />
          <span />
        </div>
      )}
      {hubs && (
        <div className="field">
          <label htmlFor="hub-filter">{t("board.filter")}</label>
          <input
            id="hub-filter"
            type="search"
            autoComplete="off"
            value={filter}
            placeholder={t("board.filterHint")}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      )}
      {hubs && hubs.filter((h) => matchesText(h.name, filter)).length === 0 && (
        <p className="muted">{t("board.noMatch")}</p>
      )}
      {hubs && (
        <ul className="hub-list">
          {hubs.filter((h) => matchesText(h.name, filter)).map((h) => (
            <li key={h.eva}>
              <Link href={`/station?eva=${h.eva}`}>{h.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

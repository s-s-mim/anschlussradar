// A small box that offers to install the app. On the start page it can be put off
// for 30 days ("Nicht jetzt"); on the help page it always shows while it applies.
// Hidden when the app is already installed or the browser can't install it.
import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { install } from "../lib/install";
import { store } from "../lib/storage";

export function InstallBox({ dismissable = true }: { dismissable?: boolean }) {
  const { t } = useI18n();
  const [, redraw] = useState(0);
  const [hidden, setHidden] = useState(() => dismissable && !store.installDue());

  useEffect(() => install.subscribe(() => redraw((n) => n + 1)), []);

  if (hidden || install.installed()) return null;
  const ios = install.isIos();
  if (!ios && !install.canPrompt()) return null;

  return (
    <aside className="install-box" aria-labelledby="install-title">
      <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
        <rect x="6" y="2.5" width="12" height="19" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 7v7m-3-3 3 3 3-3M10 18.5h4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div>
        <p id="install-title" className="install-title">
          {t("install.title")}
        </p>
        <p className="small">{ios ? t("install.ios") : t("install.lead")}</p>
        <div className="install-actions">
          {!ios && (
            <button type="button" className="primary small-btn" onClick={() => install.prompt()}>
              {t("install.button")}
            </button>
          )}
          {dismissable && (
            <button
              type="button"
              className="ghost small-btn"
              onClick={() => {
                store.installLater();
                setHidden(true);
              }}
            >
              {t("install.later")}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}

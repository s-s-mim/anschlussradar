// The app is in its test phase: before the first results, a short dialog says that
// the information comes without guarantee and where to check it. It comes back
// after 30 days. The same text stays as one line above the results and in the footer.
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { store } from "../lib/storage";

export function TestNotice() {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(() => store.noticeDue());

  useEffect(() => {
    const d = ref.current;
    if (open && d && !d.open && typeof d.showModal === "function") d.showModal();
  }, [open]);

  if (!open) return null;
  const close = () => {
    store.noticeSeen();
    ref.current?.close();
    setOpen(false);
  };
  return (
    <dialog
      ref={ref}
      className="test-notice"
      aria-labelledby="test-notice-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <h2 id="test-notice-title">{t("notice.title")}</h2>
      <p>{t("notice.body")}</p>
      <p>{t("notice.check")}</p>
      <button type="button" className="primary" onClick={close} autoFocus>
        {t("notice.ok")}
      </button>
    </dialog>
  );
}

/** One quiet line above the results. */
export function TestNote() {
  const { t } = useI18n();
  return (
    <p className="test-note small">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M12 11v6M12 7.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span>{t("notice.short")}</span>
    </p>
  );
}

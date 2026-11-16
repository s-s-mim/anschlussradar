import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useI18n } from "../i18n";
import { ApiError, sendContact } from "../lib/api";
import { Link } from "../lib/router";

const TOPICS = ["question", "feedback", "problem", "privacy", "other"] as const;
type Field = "name" | "topic" | "email" | "message";

function check(v: { name: string; topic: string; email: string; message: string }): Field | null {
  if (v.name.trim().length < 2 || v.name.trim().length > 80) return "name";
  if (!TOPICS.includes(v.topic as (typeof TOPICS)[number])) return "topic";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.email.trim())) return "email";
  if (v.message.trim().length < 10 || v.message.trim().length > 3000) return "message";
  return null;
}

export function Contact() {
  const { t } = useI18n();
  const openedAt = useRef(Date.now());
  const [values, setValues] = useState({ name: "", topic: "", email: "", message: "", website: "" });
  const [bad, setBad] = useState<Field | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [failure, setFailure] = useState<string | null>(null);

  const set = (k: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFailure(null);
    const field = check(values);
    setBad(field);
    if (field) {
      document.getElementById(`c-${field}`)?.focus();
      return;
    }
    setState("sending");
    try {
      await sendContact({ ...values, openedAt: openedAt.current });
      setState("sent");
    } catch (err) {
      setState("idle");
      if (err instanceof ApiError && err.code === "invalid_field" && err.field) setBad(err.field as Field);
      else if (err instanceof ApiError && err.status === 429) setFailure(t("contact.errors.tooMany"));
      else if (err instanceof ApiError && err.status === 0) setFailure(t("errors.offline"));
      else if (err instanceof ApiError && err.status === 503) setFailure(t("contact.errors.unavailable"));
      else setFailure(t("errors.generic"));
    }
  };

  if (state === "sent") {
    return (
      <div className="page wrap narrow">
        <h1>{t("contact.title")}</h1>
        <p className="notice ok" role="status">
          {t("contact.sent")}
        </p>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            setValues({ name: "", topic: "", email: "", message: "", website: "" });
            openedAt.current = Date.now();
            setState("idle");
          }}
        >
          {t("contact.sendAnother")}
        </button>
      </div>
    );
  }

  const err = (f: Field) =>
    bad === f ? (
      <p className="error-text" id={`c-${f}-err`}>
        {t(`contact.errors.${f}`)}
      </p>
    ) : null;
  const aria = (f: Field) => (bad === f ? { "aria-invalid": true, "aria-describedby": `c-${f}-err` } : {});

  return (
    <div className="page wrap narrow">
      <h1>{t("contact.title")}</h1>
      <p className="lead">{t("contact.lead")}</p>
      <form className="contact" onSubmit={submit} noValidate>
        <div className={`field${bad === "name" ? " invalid" : ""}`}>
          <label htmlFor="c-name">{t("contact.name")}</label>
          <input id="c-name" autoComplete="name" maxLength={80} value={values.name} onChange={set("name")} {...aria("name")} />
          {err("name")}
        </div>
        <div className={`field${bad === "email" ? " invalid" : ""}`}>
          <label htmlFor="c-email">{t("contact.email")}</label>
          <input id="c-email" type="email" autoComplete="email" value={values.email} onChange={set("email")} {...aria("email")} />
          {err("email")}
        </div>
        <div className={`field${bad === "topic" ? " invalid" : ""}`}>
          <label htmlFor="c-topic">{t("contact.topic")}</label>
          <select id="c-topic" value={values.topic} onChange={set("topic")} {...aria("topic")}>
            <option value="" disabled>
              –
            </option>
            {TOPICS.map((k) => (
              <option key={k} value={k}>
                {t(`contact.topics.${k}`)}
              </option>
            ))}
          </select>
          {err("topic")}
        </div>
        <div className={`field${bad === "message" ? " invalid" : ""}`}>
          <label htmlFor="c-message">{t("contact.message")}</label>
          <textarea id="c-message" rows={7} maxLength={3000} value={values.message} onChange={set("message")} {...aria("message")} />
          {err("message")}
        </div>
        {/* Spam trap: hidden from people and screen readers, bots fill it in. */}
        <div className="trap" aria-hidden="true">
          <label htmlFor="c-website">Website</label>
          <input id="c-website" tabIndex={-1} autoComplete="off" value={values.website} onChange={set("website")} />
        </div>
        <p className="small muted">
          {t("contact.privacyNote")} <Link href="/datenschutz">{t("nav.privacy")}</Link>
        </p>
        {failure && (
          <p className="notice error" role="alert">
            {failure}
          </p>
        )}
        <button type="submit" className="primary" disabled={state === "sending"}>
          {state === "sending" ? t("contact.sending") : t("contact.send")}
        </button>
      </form>
    </div>
  );
}

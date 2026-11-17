// The question box on the help page. Step 1: the help texts that fit, found on the
// phone. Step 2 (only if none fits): the AI answer, when it is switched on.
// Step 3: send the question to the operator, anonymously, optionally with a
// notification once it is answered. Answers show up under "Meine Fragen".
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useI18n } from "../i18n";
import { ApiError, ask, getQuestion, sendQuestion } from "../lib/api";
import type { QuestionView } from "../lib/api";
import type { HelpEntry } from "../lib/helpSearch";
import { searchHelp } from "../lib/helpSearch";
import { pushSupported, subscription } from "../lib/push";
import { Link } from "../lib/router";
import { store } from "../lib/storage";

/** Test phase: questions per phone per 24 hours. The server has the same limit. */
const PER_DAY = 2;

const sentToday = () => store.questions().filter((q) => Date.now() - Date.parse(q.sent) < 86_400_000).length;

type Step = "typing" | "asking" | "answered" | "send" | "sending" | "sent" | "sentNotify";

function Entry({ e }: { e: HelpEntry }) {
  return (
    <details className="match">
      <summary>{e.q}</summary>
      {e.a.map((p) => (
        <p key={p}>{p}</p>
      ))}
      {e.list && (
        <ul>
          {e.list.map((li) => (
            <li key={li}>{li}</li>
          ))}
        </ul>
      )}
    </details>
  );
}

export function QuestionBox({ onSent }: { onSent: () => void }) {
  const { t, lang, dict } = useI18n();
  const [text, setText] = useState("");
  const [step, setStep] = useState<Step>("typing");
  const [aiAnswer, setAiAnswer] = useState<string | null>(null);
  const [notify, setNotify] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const matches = text.trim().length >= 3 ? searchHelp(text, dict.help.items as HelpEntry[]) : [];
  const tooShort = text.trim().length < 5;

  const reset = (value: string) => {
    setText(value);
    setStep("typing");
    setAiAnswer(null);
    setProblem(null);
  };

  const tryAi = async () => {
    if (tooShort) return setProblem(t("qbox.tooShort"));
    setStep("asking");
    try {
      const r = await ask(text.trim(), lang);
      if (r.available && r.answer) {
        setAiAnswer(r.answer);
        setStep("answered");
        return;
      }
    } catch {
      // the AI step is a bonus: on any problem, offer to send the question
    }
    setStep("send");
  };

  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (tooShort) return setProblem(t("qbox.tooShort"));
    setStep("sending");
    setProblem(null);
    let sub: PushSubscriptionJSON | undefined;
    if (notify) {
      try {
        sub = await subscription();
      } catch {
        // No notifications on this device (or permission denied): send anyway,
        // the answer still shows under "Meine Fragen".
        setProblem(t("qbox.pushOff"));
      }
    }
    try {
      const r = await sendQuestion(text.trim(), lang, sub);
      store.addQuestion({ id: r.question.id, text: r.question.text, sent: new Date().toISOString() });
      setStep(r.notify ? "sentNotify" : "sent");
      setText("");
      onSent();
    } catch (err) {
      setStep("send");
      setProblem(err instanceof ApiError && err.status === 429 ? t("qbox.tooMany", { count: PER_DAY }) : t("qbox.failed"));
    }
  };

  return (
    <section className="qbox" aria-labelledby="qbox-title">
      <h2 id="qbox-title">{t("qbox.title")}</h2>
      <form onSubmit={send}>
        <label htmlFor="question">{t("qbox.label")}</label>
        <textarea
          id="question"
          rows={2}
          maxLength={500}
          value={text}
          placeholder={t("qbox.hint")}
          onChange={(e) => reset(e.target.value)}
        />

        {matches.length > 0 && step === "typing" && (
          <div className="matches">
            <p className="small muted">{t("qbox.matches")}</p>
            {matches.map((m) => (
              <Entry key={m.q} e={m} />
            ))}
          </div>
        )}

        {step === "typing" && text.trim().length >= 3 && (
          <button type="button" className="ghost" onClick={tryAi}>
            {matches.length > 0 ? t("qbox.noMatch") : t("qbox.go")}
          </button>
        )}

        {step === "asking" && (
          <p className="small muted" role="status">
            {t("qbox.thinking")}
          </p>
        )}

        {step === "answered" && aiAnswer && (
          <div className="ai-answer" role="status">
            <p>{aiAnswer}</p>
            <p className="small muted">{t("qbox.aiLabel")}</p>
            <button type="button" className="link-button" onClick={() => setStep("send")}>
              {t("qbox.notHelpful")}
            </button>
          </div>
        )}

        {step === "send" && sentToday() >= PER_DAY && (
          <p className="notice">{t("qbox.tooMany", { count: PER_DAY })}</p>
        )}

        {(step === "sending" || (step === "send" && sentToday() < PER_DAY)) && (
          <div className="send">
            <p className="small">{t("qbox.sendLead")}</p>
            <p className="small muted">{t("qbox.testPhase", { count: PER_DAY })}</p>
            {pushSupported() && (
              <label className="check">
                <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
                <span>{t("qbox.notify")}</span>
              </label>
            )}
            <button type="submit" className="primary" disabled={step === "sending"}>
              {step === "sending" ? t("qbox.sending") : t("qbox.send")}
            </button>
          </div>
        )}

        {problem && <p className="error-text">{problem}</p>}
        {(step === "sent" || step === "sentNotify") && (
          <p className="notice" role="status">
            {step === "sentNotify" ? t("qbox.sentNotify") : t("qbox.sent")}
          </p>
        )}
      </form>
    </section>
  );
}

export function MyQuestions({ version, highlight }: { version: number; highlight: string | null }) {
  const { t } = useI18n();
  const [items, setItems] = useState(store.questions());
  const [views, setViews] = useState<Record<string, QuestionView | "gone">>({});

  useEffect(() => {
    const list = store.questions();
    setItems(list);
    for (const q of list) {
      getQuestion(q.id)
        .then((v) => {
          setViews((old) => ({ ...old, [q.id]: v }));
          if (v.answer) store.markSeen(q.id); // shown here: no more hint on the start page
        })
        .catch((e: unknown) => {
          // Deleted on the server (old or spam): forget it here too.
          if (e instanceof ApiError && e.status === 404) setViews((old) => ({ ...old, [q.id]: "gone" }));
        });
    }
  }, [version]);

  const shown = items.filter((q) => views[q.id] !== "gone");
  if (shown.length === 0) return null;
  return (
    <section id="my-questions" className="my-questions">
      <h2>{t("qbox.mine")}</h2>
      <ul>
        {shown.map((q) => {
          const v = views[q.id];
          const answer = v && v !== "gone" ? v.answer : null;
          return (
            <li key={q.id} className={q.id === highlight ? "highlight" : undefined}>
              <p className="q">{q.text}</p>
              {answer ? <p className="a">{answer}</p> : <p className="small muted">{t("qbox.waiting")}</p>}
              <button
                type="button"
                className="link-button small"
                onClick={() => {
                  store.removeQuestion(q.id);
                  setItems(store.questions());
                }}
              >
                {t("qbox.remove")}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** On the start page: "Deine Frage wurde beantwortet." for answers not yet read. */
export function AnsweredHint() {
  const { t } = useI18n();
  const [answered, setAnswered] = useState<string | null>(null);

  useEffect(() => {
    // Only unread questions from the last 60 days, at most 3 requests.
    const open = store
      .questions()
      .filter((q) => !q.seen && Date.now() - Date.parse(q.sent) < 60 * 86_400_000)
      .slice(0, 3);
    for (const q of open) {
      getQuestion(q.id)
        .then((v) => {
          if (v.answer) setAnswered((cur) => cur ?? q.id);
        })
        .catch(() => undefined);
    }
  }, []);

  if (!answered) return null;
  return (
    <p className="notice answered-hint">
      {t("qbox.answeredHint")} <Link href={`/help?question=${answered}#my-questions`}>{t("qbox.read")}</Link>
    </p>
  );
}

import { useEffect, useState } from "react";
import { MyQuestions, QuestionBox } from "../components/QuestionBox";
import { useI18n } from "../i18n";
import { Link } from "../lib/router";

export function Help({ search }: { search: URLSearchParams }) {
  const { dict } = useI18n();
  const help = dict.help;
  const [version, setVersion] = useState(0);
  const highlight = search.get("question");

  useEffect(() => {
    // Opened from an answer notification: jump to the answer.
    if (highlight) document.getElementById("my-questions")?.scrollIntoView();
  }, [highlight, version]);

  return (
    <div className="page prose wrap narrow">
      <h1>{help.title}</h1>
      <QuestionBox onSent={() => setVersion((v) => v + 1)} />
      <MyQuestions version={version} highlight={highlight} />
      <h2>{dict.qbox.all}</h2>
      {help.items.map((item, i) => (
        <details key={item.q} open={i === 0}>
          <summary>{item.q}</summary>
          {item.a.map((p) => (
            <p key={p}>{p}</p>
          ))}
          {"list" in item && item.list && (
            <ul>
              {item.list.map((li) => (
                <li key={li}>{li}</li>
              ))}
            </ul>
          )}
        </details>
      ))}
      <p>
        {help.more} <Link href="/contact">{help.moreLink}</Link>
      </p>
    </div>
  );
}

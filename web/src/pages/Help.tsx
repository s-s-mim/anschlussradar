import { useI18n } from "../i18n";
import { Link } from "../lib/router";

export function Help() {
  const { dict } = useI18n();
  const help = dict.help;
  return (
    <div className="page prose wrap narrow">
      <h1>{help.title}</h1>
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

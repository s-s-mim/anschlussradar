// Station field with suggestions. Follows the ARIA combobox pattern, so it works
// with a keyboard and with screen readers.
import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useI18n } from "../i18n";
import { searchPlaces } from "../lib/api";
import type { Station } from "../lib/types";

interface Props {
  label: string;
  value: Station | null;
  onChange: (s: Station | null) => void;
  invalid?: boolean;
  autoFocus?: boolean;
  /** Also bus, tram and U-Bahn stops, not only train stations. */
  all?: boolean;
}

export function StationInput({ label, value, onChange, invalid, autoFocus, all = false }: Props) {
  const { t, lang } = useI18n();
  const id = useId();
  const [text, setText] = useState(value?.name ?? "");
  const [items, setItems] = useState<Station[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searched, setSearched] = useState("");
  const typed = useRef(false);

  // Outside changes (swap, a saved route) replace the text.
  useEffect(() => {
    if (value) setText(value.name);
    else if (!typed.current) setText("");
  }, [value]);

  useEffect(() => {
    if (!typed.current) return;
    const q = text.trim();
    if (q.length < 2) {
      setItems([]);
      setSearched("");
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setLoadingMore(false);
      try {
        // Step 1: train stations at once.
        const first = await searchPlaces(q, lang, all, "local", ctrl.signal);
        setItems(first.places);
        setActive(first.places.length ? 0 : -1);
        setLoading(false);
        if (!first.more) {
          setSearched(q);
          return;
        }
        // Step 2: stops and addresses, added when they arrive.
        setLoadingMore(true);
        const more = await searchPlaces(q, lang, all, "more", ctrl.signal).catch(() => ({ places: [] as Station[] }));
        const seen = new Set(first.places.map((p) => p.id));
        let merged = [...first.places, ...more.places.filter((p) => !seen.has(p.id))];
        if (/\d/.test(q)) merged = [...merged.filter((p) => p.kind === "address"), ...merged.filter((p) => p.kind !== "address")];
        merged = merged.slice(0, 10);
        setItems(merged);
        setActive(merged.length ? 0 : -1);
        setSearched(q);
      } catch {
        if (!ctrl.signal.aborted) setItems([]);
      } finally {
        if (!ctrl.signal.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    }, 180);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [text, all, lang]);

  const choose = (s: Station) => {
    typed.current = false;
    onChange(s);
    setText(s.name);
    setOpen(false);
    setItems([]);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? items.length - 1 : a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const listId = `${id}-list`;
  const showEmpty = open && !loading && !loadingMore && searched && !items.length && text.trim() === searched;

  return (
    <div className={`field station${invalid ? " invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        autoFocus={autoFocus}
        placeholder={t("station.placeholder")}
        aria-expanded={open && items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        value={text}
        onChange={(e) => {
          typed.current = true;
          setText(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={(e) => e.target.select()}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKey}
      />
      {open && items.length > 0 && (
        <ul id={listId} role="listbox" className="suggestions">
          {items.map((s, i) => (
            <li
              key={s.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(s);
              }}
              onMouseEnter={() => setActive(i)}
            >
              <PlaceIcon kind={s.kind} />
              <span className="place-text">
                <span>{s.name}</span>
                {s.detail && <span className="place-detail">{s.detail}</span>}
              </span>
            </li>
          ))}
          {loadingMore && (
            <li className="more-loading" aria-hidden="true">
              {t("station.searchingMore")}
            </li>
          )}
        </ul>
      )}
      {open && loadingMore && !items.length && <p className="hint">{t("station.searchingMore")}</p>}
      {showEmpty && <p className="hint">{t("station.noMatch")}</p>}
    </div>
  );
}

/** Train, stop or house: what kind of place a suggestion is, at a glance. */
export function PlaceIcon({ kind }: { kind?: string }) {
  const d =
    kind === "address"
      ? "M4 11 12 4l8 7v9h-5v-6H9v6H4Z"
      : kind === "stop"
        ? "M7 4h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm0 6h10M8 17v3m8-3v3"
        : kind === "here"
          ? "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Z"
          : "M8 3h8a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Zm-3 8h14M9 21l-2 0 2-4m6 4h2l-2-4";
  return (
    <svg className="place-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

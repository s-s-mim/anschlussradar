// Station field with suggestions. Follows the ARIA combobox pattern, so it works
// with a keyboard and with screen readers.
import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useI18n } from "../i18n";
import { searchStations } from "../lib/api";
import type { Station } from "../lib/types";

interface Props {
  label: string;
  value: Station | null;
  onChange: (s: Station | null) => void;
  invalid?: boolean;
  autoFocus?: boolean;
}

export function StationInput({ label, value, onChange, invalid, autoFocus }: Props) {
  const { t } = useI18n();
  const id = useId();
  const [text, setText] = useState(value?.name ?? "");
  const [items, setItems] = useState<Station[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
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
    const timer = setTimeout(() => {
      setLoading(true);
      searchStations(q, ctrl.signal)
        .then((list) => {
          setItems(list);
          setActive(list.length ? 0 : -1);
          setSearched(q);
        })
        .catch(() => {
          if (!ctrl.signal.aborted) setItems([]);
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [text]);

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
  const showEmpty = open && !loading && searched && !items.length && text.trim() === searched;

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
              {s.name}
            </li>
          ))}
        </ul>
      )}
      {showEmpty && <p className="hint">{t("station.noMatch")}</p>}
    </div>
  );
}

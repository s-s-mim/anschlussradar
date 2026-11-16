"""Translate DB's reason codes into the app's other languages with Azure OpenAI.

  python scripts/translate_messages.py            all languages that have no file yet
  python scripts/translate_messages.py tr uk      only these (overwrites)

Reads web/src/i18n/messages/en.json (and de.json as the original wording), asks the
model for the same 99 entries in the target language, checks that every code is
there and nothing is empty, writes <lang>.json and updates index.ts.

This runs once, by hand, not in the app: the result is a plain file that a native
speaker can review in a pull request. Cost: a few cents per language.

Needs in .env or the environment:
  AZURE_OPENAI_ENDPOINT    https://<name>.openai.azure.com
  AZURE_OPENAI_KEY         a key of that resource (keep it out of Git)
  AZURE_OPENAI_DEPLOYMENT  the deployment name, e.g. gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "web" / "src" / "i18n" / "messages"
API_VERSION = "2024-10-21"

LANGUAGES = {
    "tr": "Turkish",
    "uk": "Ukrainian",
    "pl": "Polish",
    "ru": "Russian",
    "ro": "Romanian",
    "mk": "Macedonian",
    "ar": "Arabic",
    "ur": "Urdu",
    "hi": "Hindi",
    "bn": "Bengali",
    "am": "Amharic",
}

PROMPT = """You translate short status messages for a German train app.
Each entry is a reason for a train delay or a note about the train (missing coach,
no Wi-Fi). Translate every value into {language}. Keep them short, like a station
display, in plain everyday words. Keep "1st class", "Wi-Fi" and numbers natural for
{language}. Do not translate the keys. Answer with one JSON object with exactly the
same keys.

English:
{english}

German original, for meaning:
{german}"""


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def translate(lang: str, english: dict[str, str], german: dict[str, str]) -> dict[str, str]:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    resp = httpx.post(
        f"{endpoint}/openai/deployments/{deployment}/chat/completions",
        params={"api-version": API_VERSION},
        headers={"api-key": os.environ["AZURE_OPENAI_KEY"]},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT.format(
                        language=LANGUAGES[lang],
                        english=json.dumps(english, ensure_ascii=False, indent=0),
                        german=json.dumps(german, ensure_ascii=False, indent=0),
                    ),
                }
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    result = json.loads(resp.json()["choices"][0]["message"]["content"])
    return check(result, english)


def check(result: dict[str, object], english: dict[str, str]) -> dict[str, str]:
    """Every key present, every value a non-empty string; otherwise stop."""
    missing = sorted(set(english) - set(result), key=int)
    empty = [k for k in english if k in result and not str(result[k]).strip()]
    if missing or empty:
        raise ValueError(f"incomplete translation: missing {missing}, empty {empty}")
    return {k: str(result[k]).strip() for k in sorted(english, key=int)}


INDEX = """// DB reason codes as text, per language. de.json is DB's own wording; en.json is a
// reviewed translation. The other languages are generated from en.json with
// scripts/translate_messages.py (Azure OpenAI) and listed here once they exist.
// A missing language shows English, a missing code shows nothing.
import type {{ Lang }} from "..";
{imports}

type Texts = Record<string, string>;

const TEXTS: Partial<Record<Lang, Texts>> = {{ {table} }};

export function messageText(lang: Lang, code: number): string | null {{
  const key = String(code);
  return TEXTS[lang]?.[key] ?? TEXTS.en?.[key] ?? null;
}}
"""


def write_index(langs: list[str]) -> None:
    imports = "\n".join(f'import {lang} from "./{lang}.json";' for lang in langs)
    (DIR / "index.ts").write_text(
        INDEX.format(imports=imports, table=", ".join(langs)), encoding="utf-8"
    )


def main(argv: list[str]) -> int:
    load_env()
    english = json.loads((DIR / "en.json").read_text(encoding="utf-8"))
    german = json.loads((DIR / "de.json").read_text(encoding="utf-8"))
    targets = argv or [code for code in LANGUAGES if not (DIR / f"{code}.json").exists()]
    for lang in targets:
        print(f"{lang} ({LANGUAGES[lang]}) …", flush=True)
        data = translate(lang, english, german)
        (DIR / f"{lang}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    present = ["de", "en"] + [c for c in LANGUAGES if (DIR / f"{c}.json").exists()]
    write_index(present)
    print(f"done: {', '.join(present)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

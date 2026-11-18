"""Apply every .kql file in kql/ to a Data Explorer database, in file order.

  python scripts/apply_kql.py                    # uses KUSTO_QUERY_URI and KUSTO_DATABASE
  python scripts/apply_kql.py --dry-run          # print the commands only
  python scripts/apply_kql.py --interactive      # sign in with your own account in a browser

A command starts at a line beginning with '.' and runs until the next one.
Lines starting with '//' are comments and are skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def split_commands(text: str) -> list[str]:
    commands: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        if line.startswith("."):
            if current:
                commands.append("\n".join(current).strip())
            current = [line]
        elif current:
            current.append(line)
    if current:
        commands.append("\n".join(current).strip())
    return [c for c in commands if c]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="sign in with your own account in the browser instead of the app registration",
    )
    args = parser.parse_args()

    files = sorted((ROOT / "kql").glob("*.kql"))
    commands = [(f.name, c) for f in files for c in split_commands(f.read_text("utf-8"))]
    if args.dry_run:
        for name, cmd in commands:
            print(f"-- {name}\n{cmd}\n")
        print(f"{len(commands)} commands")
        return 0

    from azure.kusto.data import KustoClient

    from anschlussradar.config import get_settings
    from anschlussradar.storage.azure import kusto_connection

    settings = get_settings()
    client = KustoClient(kusto_connection(settings.kusto_query_uri, settings, args.interactive))
    from azure.kusto.data.exceptions import KustoServiceError

    # A failing command in one file stops that file only: later files are independent
    # (each defines its own functions), so one mistake no longer hides all of them.
    failed: list[str] = []
    skip_file = ""
    for i, (name, cmd) in enumerate(commands, start=1):
        first_line = cmd.splitlines()[0][:90]
        if name == skip_file:
            print(f"[{i}/{len(commands)}] {name}: skipped after an earlier error in this file")
            continue
        print(f"[{i}/{len(commands)}] {name}: {first_line}")
        try:
            client.execute_mgmt(settings.kusto_database, cmd)
        except KustoServiceError as exc:
            # The whole failing command and the server's short message, not a long stack
            # trace. Every command is idempotent, so a rerun after the fix is safe.
            print(f"\nFAILED in {name}, command {i}:\n\n{cmd}\n")
            print(f"Error: {exc}"[:2000])
            failed.append(name)
            skip_file = name
    if failed:
        print(f"\n{len(failed)} file(s) failed: {', '.join(failed)}")
        return 1
    print(f"applied {len(commands)} commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

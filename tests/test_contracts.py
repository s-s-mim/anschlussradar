"""The parser's records must match the Data Explorer tables column for column.

A mismatch here would mean silently empty columns after ingestion.
"""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from anschlussradar.db_api.parser import parse_changes, parse_plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 4, 7, 0, tzinfo=UTC)


def _tables() -> dict[str, list[tuple[str, str]]]:
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "gen_kql_tables.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TABLES  # type: ignore[no-any-return]


def _columns(table: str) -> set[str]:
    return {c for c, _ in _tables()[table]}


def test_planned_stop_record_matches_table() -> None:
    record = parse_plan((FIXTURES / "plan_frankfurt.xml").read_bytes())[0].to_record(NOW)
    assert set(record) == _columns("PlannedStops")


def test_change_record_matches_table() -> None:
    change = parse_changes((FIXTURES / "changes_frankfurt.xml").read_bytes())[0]
    assert set(change.to_record(NOW, "rchg")) == _columns("StopChangeEvents")


def test_ingestion_log_columns() -> None:
    from anschlussradar.ingest import jobs

    source = Path(jobs.__file__).read_text()
    for column in _columns("IngestionLog"):
        assert f'"{column}"' in source


def test_generated_kql_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "gen_kql_tables.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (ROOT / "kql" / "01_tables.kql").read_text(encoding="utf-8") == module.render()


def test_shared_kql_is_generated_from_python() -> None:
    spec = importlib.util.spec_from_file_location(
        "gen_shared", ROOT / "scripts" / "gen_kql_shared.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (ROOT / "kql" / "00_shared.kql").read_text(encoding="utf-8") == module.render()

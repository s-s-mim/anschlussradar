"""Export training data from Data Explorer to a Parquet file.

  python -m anschlussradar.ml.export --days 120 --out data/training/transfers.parquet

Uses KUSTO_QUERY_URI, KUSTO_DATABASE and the KUSTO_APP_* settings from .env or the
environment. The query is the TransferTrainingData() function in kql/04_ml.kql.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import get_settings


def export(days: int, out: Path) -> int:
    from azure.kusto.data import ClientRequestProperties, KustoClient
    from azure.kusto.data.helpers import dataframe_from_result_table

    from ..storage.azure import kusto_connection

    settings = get_settings()
    client = KustoClient(kusto_connection(settings.kusto_query_uri, settings))
    props = ClientRequestProperties()
    props.set_option("servertimeout", "00:10:00")
    # The free cluster limits result size; truncation is switched off for the export.
    props.set_option("notruncation", True)
    query = f"TransferTrainingData(ago({int(days)}d), now())"
    response = client.execute_query(settings.kusto_database, query, props)
    df = dataframe_from_result_table(response.primary_results[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    logging.info("exported %d rows to %s", len(df), out)
    return len(df)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anschlussradar-export")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("data/training/transfers.parquet"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = export(args.days, args.out)
    return 0 if rows > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

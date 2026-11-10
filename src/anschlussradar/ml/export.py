"""Export training data from Data Explorer to a Parquet file.

  python -m anschlussradar.ml.export --days 120 --out data/training/transfers.parquet

Uses KUSTO_QUERY_URI, KUSTO_DATABASE and the KUSTO_APP_* settings from .env or the
environment. The query is the TransferTrainingData() function in kql/04_ml.kql.
"""

from __future__ import annotations

import argparse
import logging
from datetime import timedelta
from pathlib import Path

from ..config import get_settings


def export(days: int, out: Path) -> int:
    from azure.kusto.data import ClientRequestProperties, KustoClient
    from azure.kusto.data.helpers import dataframe_from_result_table

    from ..storage.azure import kusto_connection

    settings = get_settings()
    client = KustoClient(kusto_connection(settings.kusto_query_uri, settings))
    props = ClientRequestProperties()
    # The SDK expects a timedelta here, not a "hh:mm:ss" string.
    props.set_option(ClientRequestProperties.request_timeout_option_name, timedelta(minutes=10))
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
    if rows == 0:
        # Not an error: early on there are no transfers yet. The training step then
        # reports "fewer than 3 weeks of data" and keeps the app in live_only.
        logging.warning("no training rows yet; the training step will wait for more data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

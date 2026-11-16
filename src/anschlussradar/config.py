"""Settings, read from environment variables or a local .env file.

In Azure the same names are set as Function App settings. Secrets are
Key Vault references there, e.g.
DB_API_KEY=@Microsoft.KeyVault(SecretUri=https://kv-ar-prod.vault.azure.net/secrets/db-api-key/)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # DB API Marketplace credentials (Timetables API, free plan)
    db_client_id: str = Field(default="", alias="DB_CLIENT_ID")
    db_api_key: str = Field(default="", alias="DB_API_KEY")
    db_base_url: str = Field(
        default="https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1",
        alias="DB_BASE_URL",
    )
    db_requests_per_minute: int = Field(default=60, alias="DB_REQUESTS_PER_MINUTE")

    # Where to write: "local" for development, "azure" in the cloud
    sink: Literal["local", "azure"] = Field(default="local", alias="SINK")
    local_data_dir: Path = Field(default=Path("data"), alias="LOCAL_DATA_DIR")

    # Azure Blob Storage (bronze layer)
    blob_account_url: str = Field(default="", alias="BLOB_ACCOUNT_URL")
    blob_container: str = Field(default="raw", alias="BLOB_CONTAINER")

    # Azure Data Explorer (silver and gold layers)
    kusto_ingest_uri: str = Field(default="", alias="KUSTO_INGEST_URI")
    kusto_query_uri: str = Field(default="", alias="KUSTO_QUERY_URI")
    kusto_database: str = Field(default="anschlussradar", alias="KUSTO_DATABASE")
    # The free cluster is not part of an Azure subscription, so managed identity
    # cannot be granted there. Use an Entra app registration instead.
    kusto_app_id: str = Field(default="", alias="KUSTO_APP_ID")
    kusto_app_secret: str = Field(default="", alias="KUSTO_APP_SECRET")
    kusto_tenant_id: str = Field(default="", alias="KUSTO_TENANT_ID")

    # Recording list
    hubs_file: Path = Field(default=Path("config/hubs.csv"), alias="HUBS_FILE")

    # Weather (Bright Sky, open DWD data). Hub coordinates come from the station list.
    weather_base_url: str = Field(default="https://api.brightsky.dev", alias="WEATHER_BASE_URL")
    models_base_url: str = Field(default="", alias="MODELS_BASE_URL")

    # Identifies this app to external services. Generic on purpose.
    user_agent: str = Field(
        default="AnschlussRadar/0.1 (+https://github.com/s-s-mim/anschlussradar)",
        alias="USER_AGENT",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

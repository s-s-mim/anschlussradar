"""Settings for the API Function App (separate from the ingestion settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .. import __version__


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Transitous (journey planning). Its usage policy asks every client to identify
    # itself with app name, version and a contact (e-mail or website).
    transitous_base_url: str = Field(
        default="https://api.transitous.org", alias="TRANSITOUS_BASE_URL"
    )
    transitous_contact: str = Field(
        default="https://github.com/s-s-mim/anschlussradar", alias="TRANSITOUS_CONTACT"
    )
    plan_cache_seconds: int = Field(default=120, alias="PLAN_CACHE_SECONDS")

    # Public files in the models container: stations.json and the model registry.
    models_base_url: str = Field(default="", alias="MODELS_BASE_URL")
    stations_path: str = Field(default="stations/stations.json", alias="STATIONS_PATH")
    hubs_file: str = Field(default="config/hubs.csv", alias="HUBS_FILE")

    # History counts for scores (Data Explorer). Empty = scores without history.
    kusto_query_uri: str = Field(default="", alias="KUSTO_QUERY_URI")
    kusto_database: str = Field(default="anschlussradar", alias="KUSTO_DATABASE")
    # The same app registration as the poller; it already has the Viewer role.
    kusto_app_id: str = Field(default="", alias="KUSTO_APP_ID")
    kusto_app_secret: str = Field(default="", alias="KUSTO_APP_SECRET")
    kusto_tenant_id: str = Field(default="", alias="KUSTO_TENANT_ID")

    # Contact form: Azure Communication Services Email.
    acs_endpoint: str = Field(default="", alias="ACS_ENDPOINT")
    acs_connection_string: str = Field(default="", alias="ACS_CONNECTION_STRING")
    contact_from: str = Field(default="", alias="CONTACT_FROM_ADDRESS")
    contact_to: str = Field(default="", alias="CONTACT_TO_ADDRESS")

    @property
    def user_agent(self) -> str:
        return f"AnschlussRadar/{__version__} (+{self.transitous_contact})"


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    return ApiSettings()

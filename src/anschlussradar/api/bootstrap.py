"""Build the ApiService from settings, once per Function App instance."""

from __future__ import annotations

import logging
from pathlib import Path

from ..ingest.hubs import load_hubs
from ..ml.registry import HttpReadStore, LocalStore, ModelRegistry
from ..ml.serving import ModelHolder
from .contact import AcsEmailSender, EmailSender
from .feedback import BlobFeedbackStore, FeedbackStore
from .history import KustoHistory, kusto_query
from .journeys import HistoryProvider, NoHistory
from .service import ApiService
from .settings import ApiSettings
from .stations import HubMatcher, StationIndex
from .transitous import TransitousClient

log = logging.getLogger(__name__)


def build_service(settings: ApiSettings, local_models_dir: Path | None = None) -> ApiService:
    store = (
        LocalStore(local_models_dir)
        if local_models_dir is not None
        else HttpReadStore(settings.models_base_url)
    )

    stations = StationIndex([])
    try:
        data = store.read(settings.stations_path)
        if data:
            stations = StationIndex.from_json(data)
        else:
            log.warning("no %s yet; station search is empty", settings.stations_path)
    except Exception:
        log.exception("could not load the station list")

    history: HistoryProvider = NoHistory()
    if settings.kusto_query_uri:
        history = KustoHistory(
            kusto_query(
                settings.kusto_query_uri,
                settings.kusto_database,
                settings.kusto_app_id,
                settings.kusto_app_secret,
                settings.kusto_tenant_id,
            )
        )

    email: EmailSender | None = None
    if (
        settings.contact_to
        and settings.contact_from
        and (settings.acs_endpoint or settings.acs_connection_string)
    ):
        email = AcsEmailSender(
            settings.contact_from,
            settings.contact_to,
            settings.acs_endpoint,
            settings.acs_connection_string,
        )

    feedback: FeedbackStore | None = None
    if settings.feedback_account_url:
        try:
            feedback = BlobFeedbackStore(settings.feedback_account_url, settings.feedback_container)
        except Exception:
            log.exception("could not set up the feedback store")

    return ApiService(
        stations=stations,
        hubs=HubMatcher(load_hubs(Path(settings.hubs_file))),
        transitous=TransitousClient(
            settings.transitous_base_url, settings.user_agent, settings.plan_cache_seconds
        ),
        models=ModelHolder(ModelRegistry(store)),
        history=history,
        email=email,
        feedback=feedback,
    )

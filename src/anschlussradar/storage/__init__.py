"""Writers for the bronze (raw files) and silver (tables) layers."""

from __future__ import annotations

from ..config import Settings
from .base import Sink


def make_sink(settings: Settings) -> Sink:
    if settings.sink == "azure":
        from .azure import AzureSink

        return AzureSink(settings)
    from .local import LocalSink

    return LocalSink(settings.local_data_dir)


__all__ = ["Sink", "make_sink"]

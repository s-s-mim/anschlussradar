"""Model serving for the API: hourly refresh, calibration, scores and the status endpoint.

  holder = ModelHolder(ModelRegistry(HttpReadStore(MODELS_BASE_URL)))
  result = score_transfer(holder.get(), transfer_input, history_counts)
  status = model_status(holder)          # body of GET /api/v1/model/status
"""

from __future__ import annotations

import bisect
import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    HistoryCounts,
    TransferInput,
    confidence_label,
    feature_vector,
)
from .registry import ModelRegistry
from .stages import Stage

log = logging.getLogger(__name__)

# A scorer turns a feature matrix into raw probabilities of "made".
Scorer = Callable[[Sequence[Sequence[float]]], list[float]]
ScorerFactory = Callable[[bytes], Scorer]


def onnx_scorer(model_bytes: bytes) -> Scorer:
    """Load an ONNX model exported with zipmap=False (output 1 is an n x 2 array)."""
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    def score(rows: Sequence[Sequence[float]]) -> list[float]:
        x = np.asarray(rows, dtype=np.float32)
        outputs = session.run(None, {input_name: x})
        probabilities = outputs[1]
        return [float(v) for v in np.asarray(probabilities)[:, 1]]

    return score


@dataclass(frozen=True)
class Calibration:
    """Isotonic regression stored as a step table; applied by linear interpolation."""

    x: tuple[float, ...]
    y: tuple[float, ...]

    def apply(self, p: float) -> float:
        if not self.x:
            return p
        if p <= self.x[0]:
            return self.y[0]
        if p >= self.x[-1]:
            return self.y[-1]
        i = bisect.bisect_right(self.x, p)
        x0, x1, y0, y1 = self.x[i - 1], self.x[i], self.y[i - 1], self.y[i]
        return y0 if x1 == x0 else y0 + (y1 - y0) * (p - x0) / (x1 - x0)

    @classmethod
    def from_json(cls, data: bytes | None) -> Calibration:
        if not data:
            return cls((), ())
        doc = json.loads(data)
        return cls(tuple(doc["x"]), tuple(doc["y"]))


@dataclass(frozen=True)
class LoadedModel:
    version: str | None
    stage: Stage
    scorer: Scorer | None
    calibration: Calibration
    manifest: dict[str, Any]

    def predict(self, rows: Sequence[Sequence[float]]) -> list[float]:
        if self.scorer is None:
            raise RuntimeError("no model loaded")
        return [self.calibration.apply(p) for p in self.scorer(rows)]


NO_MODEL = LoadedModel(None, Stage.LIVE_ONLY, None, Calibration((), ()), {})


class ModelHolder:
    """Keeps the live model in memory and checks current.json at most once an hour."""

    def __init__(
        self,
        registry: ModelRegistry,
        scorer_factory: ScorerFactory = onnx_scorer,
        refresh_s: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.scorer_factory = scorer_factory
        self.refresh_s = refresh_s
        self.clock = clock
        self._model = NO_MODEL
        self._checked_at: float | None = None
        self._lock = threading.Lock()

    def get(self) -> LoadedModel:
        now = self.clock()
        if self._checked_at is None or now - self._checked_at >= self.refresh_s:
            with self._lock:
                if self._checked_at is None or now - self._checked_at >= self.refresh_s:
                    self._refresh()
                    self._checked_at = now
        return self._model

    def _refresh(self) -> None:
        try:
            pointer = self.registry.current()
        except Exception:  # network trouble: keep serving the model we have
            log.exception("could not read current.json, keeping %s", self._model.version)
            return
        if not pointer or not pointer.get("version"):
            stage = Stage(pointer["stage"]) if pointer else Stage.LIVE_ONLY
            self._model = LoadedModel(None, stage, None, Calibration((), ()), {})
            return

        version, stage = pointer["version"], Stage(pointer["stage"])
        if version == self._model.version:
            if stage is not self._model.stage:  # stage can change without a new model
                m = self._model
                self._model = LoadedModel(m.version, stage, m.scorer, m.calibration, m.manifest)
            return
        try:
            manifest = self.registry.read_json(version, "manifest.json") or {}
            if manifest.get("feature_version") != FEATURE_VERSION:
                raise ValueError(
                    f"model {version} uses feature version {manifest.get('feature_version')}, "
                    f"this code computes version {FEATURE_VERSION}"
                )
            model_bytes = self.registry.read_file(version, "model.onnx")
            if model_bytes is None:
                raise FileNotFoundError(f"model.onnx missing for {version}")
            self._model = LoadedModel(
                version=version,
                stage=stage,
                scorer=self.scorer_factory(model_bytes),
                calibration=Calibration.from_json(
                    self.registry.read_file(version, "calibration.json")
                ),
                manifest=manifest,
            )
            log.info("loaded model %s, stage %s", version, stage.value)
        except Exception:
            log.exception("could not load model %s, keeping %s", version, self._model.version)


@dataclass(frozen=True, slots=True)
class TransferScore:
    probability: float | None  # None in the live_only stage
    confidence: str  # limited, medium, high
    observations: int
    stage: Stage
    early_estimate: bool


def score_transfer(model: LoadedModel, t: TransferInput, h: HistoryCounts) -> TransferScore:
    n = int(h.exact_n)
    if model.stage is Stage.LIVE_ONLY or model.scorer is None:
        return TransferScore(None, confidence_label(n), n, Stage.LIVE_ONLY, False)
    p = model.predict([feature_vector(t, h)])[0]
    return TransferScore(round(p, 3), confidence_label(n), n, model.stage, model.stage is Stage.EARLY)


@dataclass(frozen=True, slots=True)
class LiveCheck:
    remaining_slack_min: int  # minutes left over after the minimum transfer time
    status: str  # ok, tight, at_risk, missed


def live_check(
    planned_buffer_min: int, in_delay_min: int, out_delay_min: int, min_transfer_min: int
) -> LiveCheck:
    """Day-one rule for live mode: works without any history.

    The departing train's delay helps the passenger, the arriving train's delay hurts.
    """
    remaining = planned_buffer_min - in_delay_min + max(out_delay_min, 0) - min_transfer_min
    if remaining < 0:
        status = "missed"
    elif remaining < 2:
        status = "at_risk"
    elif remaining < 5:
        status = "tight"
    else:
        status = "ok"
    return LiveCheck(remaining, status)


def model_status(holder: ModelHolder) -> dict[str, Any]:
    """Body of GET /api/v1/model/status. The web app shows the banner unless stage is full."""
    model = holder.get()
    manifest = model.manifest
    return {
        "stage": model.stage.value,
        "show_banner": model.stage is not Stage.FULL,
        "model_version": model.version,
        "trained_from": manifest.get("data_from"),
        "trained_to": manifest.get("data_to"),
        "weeks_of_data": manifest.get("weeks_of_data"),
        "metrics": manifest.get("metrics"),
        "features": list(FEATURE_NAMES),
    }

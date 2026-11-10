import json
from pathlib import Path

import pytest

from anschlussradar.ml.features import FEATURE_VERSION, HistoryCounts, TransferInput
from anschlussradar.ml.registry import LocalStore, ModelRegistry
from anschlussradar.ml.serving import (
    Calibration,
    ModelHolder,
    live_check,
    model_status,
    score_transfer,
)
from anschlussradar.ml.stages import Stage

T = TransferInput(
    planned_buffer_min=8, min_transfer_min=5, hour=7, weekday=1, in_group="sbahn", out_group="long"
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def fake_scorer(model_bytes: bytes):  # type: ignore[no-untyped-def]
    value = float(model_bytes.decode())
    return lambda rows: [value for _ in rows]


def _publish(
    reg: ModelRegistry,
    version: str,
    value: float,
    stage: str,
    feature_version: int = FEATURE_VERSION,
) -> None:
    reg.save_version(
        version,
        {
            "model.onnx": str(value).encode(),
            "calibration.json": json.dumps({"x": [0.0, 1.0], "y": [0.0, 1.0]}).encode(),
            "manifest.json": json.dumps(
                {"feature_version": feature_version, "weeks_of_data": 7}
            ).encode(),
        },
    )
    reg.set_current(version, stage)


def test_no_model_means_live_only(tmp_path: Path) -> None:
    holder = ModelHolder(ModelRegistry(LocalStore(tmp_path)), fake_scorer)
    status = model_status(holder)
    assert status["stage"] == "live_only" and status["show_banner"] is True
    assert score_transfer(holder.get(), T, HistoryCounts()).probability is None


def test_loads_model_and_refreshes_hourly(tmp_path: Path) -> None:
    reg = ModelRegistry(LocalStore(tmp_path))
    _publish(reg, "v1", 0.7, "early")
    clock = FakeClock()
    holder = ModelHolder(reg, fake_scorer, refresh_s=3600, clock=clock)

    score = score_transfer(holder.get(), T, HistoryCounts(exact_n=3))
    assert score.probability == pytest.approx(0.7)
    assert score.early_estimate and score.confidence == "limited"

    _publish(reg, "v2", 0.9, "full")
    clock.t = 1800
    assert holder.get().version == "v1"  # not yet an hour
    clock.t = 3600
    assert holder.get().version == "v2"
    status = model_status(holder)
    assert status["stage"] == "full" and status["show_banner"] is False


def test_stage_change_without_new_model(tmp_path: Path) -> None:
    reg = ModelRegistry(LocalStore(tmp_path))
    _publish(reg, "v1", 0.7, "full")
    clock = FakeClock()
    holder = ModelHolder(reg, fake_scorer, clock=clock)
    assert holder.get().stage is Stage.FULL
    reg.set_current("v1", "early", reason="champion degraded")
    clock.t = 3600
    assert holder.get().stage is Stage.EARLY
    assert model_status(holder)["show_banner"] is True


def test_incompatible_model_is_not_loaded(tmp_path: Path) -> None:
    reg = ModelRegistry(LocalStore(tmp_path))
    _publish(reg, "v1", 0.7, "early")
    clock = FakeClock()
    holder = ModelHolder(reg, fake_scorer, clock=clock)
    holder.get()
    _publish(reg, "v2", 0.9, "full", feature_version=FEATURE_VERSION + 1)
    clock.t = 3600
    assert holder.get().version == "v1"  # keeps serving the model it can compute features for


def test_calibration_interpolates_and_clips() -> None:
    cal = Calibration((0.2, 0.6), (0.3, 0.7))
    assert cal.apply(0.1) == 0.3
    assert cal.apply(0.4) == pytest.approx(0.5)
    assert cal.apply(0.9) == 0.7


@pytest.mark.parametrize(
    ("buffer", "in_delay", "out_delay", "status"),
    [
        (10, 0, 0, "ok"),
        (10, 3, 0, "tight"),
        (10, 4, 0, "at_risk"),
        (10, 6, 0, "missed"),
        (10, 6, 4, "tight"),
    ],
)
def test_live_check(buffer: int, in_delay: int, out_delay: int, status: str) -> None:
    assert live_check(buffer, in_delay, out_delay, min_transfer_min=5).status == status

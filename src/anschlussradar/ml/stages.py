"""Release stages and the champion/challenger promotion rule.

  live_only  no model is good enough yet: live delays only, learning banner
  early      model beats the baseline and is roughly calibrated: "early estimate", banner
  full       model meets the ship criteria on at least 6 weeks of data: no banner
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .metrics import Metrics


class Stage(StrEnum):
    LIVE_ONLY = "live_only"
    EARLY = "early"
    FULL = "full"

    @property
    def rank(self) -> int:
        return {"live_only": 0, "early": 1, "full": 2}[self.value]


# Criteria from section 7 of the project documentation.
EARLY_MAX_CALIBRATION_ERROR = 0.10
EARLY_MIN_TEST_ROWS = 1000
FULL_MIN_AUC_GAIN = 0.03
FULL_MAX_CALIBRATION_ERROR = 0.05
FULL_MIN_WEEKS = 6
# A challenger may be this much worse than the champion and still be promoted,
# so that noise in one test week does not block fresh models forever.
BRIER_TOLERANCE = 0.002
AUC_TOLERANCE = 0.01


@dataclass(frozen=True, slots=True)
class Evaluation:
    """A model and baseline A, both scored on the same unseen test week."""

    model: Metrics
    baseline: Metrics
    weeks_of_data: int


def stage_for(ev: Evaluation | None) -> Stage:
    if ev is None:
        return Stage.LIVE_ONLY
    m, b = ev.model, ev.baseline
    full = (
        ev.weeks_of_data >= FULL_MIN_WEEKS
        and m.auc >= b.auc + FULL_MIN_AUC_GAIN
        and m.brier < b.brier
        and m.calibration_error < FULL_MAX_CALIBRATION_ERROR
    )
    if full:
        return Stage.FULL
    early = (
        m.n >= EARLY_MIN_TEST_ROWS
        and m.auc > b.auc
        and m.calibration_error < EARLY_MAX_CALIBRATION_ERROR
    )
    return Stage.EARLY if early else Stage.LIVE_ONLY


@dataclass(frozen=True, slots=True)
class Decision:
    promote: bool
    stage: Stage  # the stage the app is in after this run
    reason: str
    stage_dropped: bool = False


def decide(
    challenger: Evaluation,
    champion: Evaluation | None,
    previous_stage: Stage | None = None,
    pinned: bool = False,
) -> Decision:
    """Promote the challenger or keep the champion."""
    ch_stage = stage_for(challenger)
    cp_stage = stage_for(champion)

    def done(promote: bool, stage: Stage, reason: str) -> Decision:
        dropped = previous_stage is not None and stage.rank < previous_stage.rank
        return Decision(promote, stage, reason, dropped)

    if pinned:
        return done(False, cp_stage, "current version is pinned")

    if champion is None:
        if ch_stage is Stage.LIVE_ONLY:
            return done(False, Stage.LIVE_ONLY, "first model does not meet the early criteria yet")
        return done(True, ch_stage, f"first model, stage {ch_stage.value}")

    if ch_stage is Stage.LIVE_ONLY:
        return done(False, cp_stage, "challenger does not meet the early criteria")
    if ch_stage.rank < cp_stage.rank:
        return done(False, cp_stage, f"challenger is {ch_stage.value}, champion is {cp_stage.value}")

    as_good = (
        challenger.model.brier <= champion.model.brier + BRIER_TOLERANCE
        and challenger.model.auc >= champion.model.auc - AUC_TOLERANCE
    )
    if as_good or ch_stage.rank > cp_stage.rank:
        return done(True, ch_stage, f"challenger promoted, stage {ch_stage.value}")
    return done(
        False,
        cp_stage,
        (
            f"challenger worse than champion (Brier {challenger.model.brier:.4f} vs "
            f"{champion.model.brier:.4f}, AUC {challenger.model.auc:.3f} vs "
            f"{champion.model.auc:.3f})"
        ),
    )

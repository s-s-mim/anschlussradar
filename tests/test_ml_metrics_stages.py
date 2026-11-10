import pytest

from anschlussradar.ml.metrics import Metrics, brier, calibration_error, evaluate, roc_auc
from anschlussradar.ml.stages import Evaluation, Stage, decide, stage_for


def test_auc_perfect_random_and_ties() -> None:
    assert roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert roc_auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_auc_matches_sklearn() -> None:
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    y = [0, 1, 1, 0, 1, 0, 1, 1, 0, 0]
    p = [0.2, 0.7, 0.7, 0.4, 0.9, 0.1, 0.3, 0.8, 0.7, 0.2]
    assert roc_auc(y, p) == pytest.approx(sklearn_metrics.roc_auc_score(y, p))


def test_brier_and_calibration() -> None:
    assert brier([1, 0], [1.0, 0.0]) == 0.0
    # 10 predictions of 0.8, 8 of them made: perfectly calibrated
    assert calibration_error([1] * 8 + [0] * 2, [0.8] * 10) == pytest.approx(0.0)
    assert calibration_error([1] * 5 + [0] * 5, [0.8] * 10) == pytest.approx(0.3)


def _m(auc: float, brier_: float, ece: float, n: int = 5000) -> Metrics:
    return Metrics(auc=auc, brier=brier_, calibration_error=ece, n=n, positive_rate=0.8)


BASE = _m(0.70, 0.150, 0.02)


def test_stage_rules() -> None:
    assert stage_for(None) is Stage.LIVE_ONLY
    assert stage_for(Evaluation(_m(0.69, 0.14, 0.03), BASE, 8)) is Stage.LIVE_ONLY  # below baseline
    assert (
        stage_for(Evaluation(_m(0.72, 0.14, 0.12), BASE, 8)) is Stage.LIVE_ONLY
    )  # badly calibrated
    assert (
        stage_for(Evaluation(_m(0.72, 0.14, 0.06, n=500), BASE, 8)) is Stage.LIVE_ONLY
    )  # too few rows
    assert stage_for(Evaluation(_m(0.72, 0.14, 0.06), BASE, 8)) is Stage.EARLY
    assert stage_for(Evaluation(_m(0.75, 0.14, 0.03), BASE, 3)) is Stage.EARLY  # only 3 weeks
    assert stage_for(Evaluation(_m(0.75, 0.14, 0.03), BASE, 6)) is Stage.FULL


def test_first_model_promoted_only_when_good_enough() -> None:
    weak = Evaluation(_m(0.65, 0.16, 0.03), BASE, 2)
    good = Evaluation(_m(0.72, 0.14, 0.06), BASE, 2)
    assert decide(weak, None).promote is False
    d = decide(good, None)
    assert d.promote and d.stage is Stage.EARLY


def test_challenger_within_tolerance_is_promoted() -> None:
    champion = Evaluation(_m(0.76, 0.130, 0.03), BASE, 6)
    challenger = Evaluation(_m(0.755, 0.1315, 0.03), BASE, 7)
    assert decide(challenger, champion, Stage.FULL).promote


def test_worse_challenger_is_rejected_and_champion_keeps_stage() -> None:
    champion = Evaluation(_m(0.78, 0.120, 0.03), BASE, 6)
    challenger = Evaluation(_m(0.74, 0.135, 0.03), BASE, 7)
    d = decide(challenger, champion, Stage.FULL)
    assert not d.promote and d.stage is Stage.FULL and not d.stage_dropped


def test_stage_drops_when_champion_degrades_and_challenger_is_weak() -> None:
    champion = Evaluation(_m(0.71, 0.145, 0.06), BASE, 6)  # now only early
    challenger = Evaluation(_m(0.60, 0.170, 0.03), BASE, 7)
    d = decide(challenger, champion, Stage.FULL)
    assert not d.promote and d.stage is Stage.EARLY and d.stage_dropped


def test_pinned_blocks_promotion() -> None:
    champion = Evaluation(_m(0.72, 0.14, 0.06), BASE, 6)
    challenger = Evaluation(_m(0.80, 0.11, 0.02), BASE, 7)
    assert decide(challenger, champion, Stage.EARLY, pinned=True).promote is False


def test_evaluate_clips_probabilities() -> None:
    m = evaluate([1, 0], [1.2, -0.1])
    assert m.brier == 0.0

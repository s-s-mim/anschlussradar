"""Model metrics in plain Python, so the API and tests need no numpy or sklearn."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Metrics:
    auc: float
    brier: float
    calibration_error: float
    n: int
    positive_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Metrics:
        return cls(**{k: d[k] for k in ("auc", "brier", "calibration_error", "n", "positive_rate")})


def roc_auc(y: Sequence[int], p: Sequence[float]) -> float:
    """Area under the ROC curve via ranks (Mann-Whitney U), ties get average ranks."""
    pairs = sorted(zip(p, y, strict=True))
    n_pos = sum(1 for _, label in pairs if label)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        rank_sum += avg_rank * sum(1 for k in range(i, j + 1) if pairs[k][1])
        i = j + 1
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def brier(y: Sequence[int], p: Sequence[float]) -> float:
    return sum((pi - yi) ** 2 for yi, pi in zip(y, p, strict=True)) / max(len(y), 1)


def calibration_error(y: Sequence[int], p: Sequence[float], bins: int = 10) -> float:
    """Expected calibration error: weighted gap between predicted and observed rate per bin."""
    totals = [0] * bins
    pred_sum = [0.0] * bins
    obs_sum = [0.0] * bins
    for yi, pi in zip(y, p, strict=True):
        b = min(int(pi * bins), bins - 1)
        totals[b] += 1
        pred_sum[b] += pi
        obs_sum[b] += yi
    n = sum(totals)
    if n == 0:
        return 0.0
    return sum(abs(pred_sum[b] - obs_sum[b]) for b in range(bins) if totals[b]) / n


def evaluate(y: Sequence[int], p: Sequence[float]) -> Metrics:
    y_list = [int(v) for v in y]
    p_list = [min(max(float(v), 0.0), 1.0) for v in p]
    return Metrics(
        auc=roc_auc(y_list, p_list),
        brier=brier(y_list, p_list),
        calibration_error=calibration_error(y_list, p_list),
        n=len(y_list),
        positive_rate=sum(y_list) / max(len(y_list), 1),
    )

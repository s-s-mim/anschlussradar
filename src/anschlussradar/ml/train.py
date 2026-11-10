"""Weekly training run: train a challenger, compare it with the champion, promote or keep.

  python -m anschlussradar.ml.train --data data/training/transfers.parquet --store local
  python -m anschlussradar.ml.train --data transfers.parquet --store blob \
      --blob-account-url https://<models account>.blob.core.windows.net

Steps
  1. Add point-in-time history counts (only days before each row's service day).
  2. Split by week: train on all but the last two weeks, calibrate on the second to
     last, test on the last week. Nothing is split randomly.
  3. Fit each candidate model (logistic regression and LightGBM), keep the one with the
     lowest Brier score on the validation week, fit isotonic calibration on that week.
     With little data the simple model usually wins; LightGBM takes over as data grows.
  4. Score challenger, champion and baseline A on the same test week.
  5. Decide with stages.decide(), save the version, write status.json, then current.json.

Exit codes: 0 ok, 2 challenger rejected while a champion exists, 3 stage dropped.
A non-zero exit fails the GitHub Actions job, and GitHub sends an e-mail.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .features import (
    DEFAULT_GLOBAL_RATE,
    FEATURE_NAMES,
    FEATURE_VERSION,
    HISTORY_DAYS,
    HistoryCounts,
    TransferInput,
    feature_vector,
)
from .metrics import Metrics, evaluate
from .registry import BlobStore, LocalStore, ModelRegistry, new_version_id
from .serving import Calibration, ScorerFactory, onnx_scorer
from .stages import Decision, Evaluation, Stage, decide

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

log = logging.getLogger(__name__)

EXACT_KEYS = ["eva", "in_number", "out_number"]
GROUP_KEYS = ["eva", "in_group", "out_group", "buffer_bucket"]
REQUIRED_COLUMNS = {
    "service_day", "eva", "in_number", "out_number", "in_group", "out_group",
    "buffer_bucket", "planned_buffer_min", "min_transfer_min", "hour", "weekday", "made",
}  # fmt: skip
MIN_WEEKS = 3  # train, validation and test need at least one week each


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TrainableModel(Protocol):
    def fit(self, x: np.ndarray, y: np.ndarray, x_val: np.ndarray, y_val: np.ndarray) -> None: ...

    def predict_proba(self, x: np.ndarray) -> np.ndarray: ...

    def export(self) -> bytes: ...


class LogisticModel:
    """Scaled logistic regression: robust with few weeks of data, exported to ONNX."""

    kind = "logistic_regression"

    def __init__(self) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self.model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))

    def fit(self, x: np.ndarray, y: np.ndarray, x_val: np.ndarray, y_val: np.ndarray) -> None:
        self.model.fit(x, y)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(x)[:, 1]  # type: ignore[no-any-return]

    def export(self) -> bytes:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        from sklearn.linear_model import LogisticRegression

        onnx_model = convert_sklearn(
            self.model,
            initial_types=[("input", FloatTensorType([None, len(FEATURE_NAMES)]))],
            options={LogisticRegression: {"zipmap": False}},
            target_opset=15,
        )
        return onnx_model.SerializeToString()  # type: ignore[no-any-return]


class LightGBMModel:
    """Gradient boosted trees, early stopping on the validation week, exported to ONNX."""

    kind = "lightgbm"

    def __init__(self) -> None:
        import lightgbm as lgb

        self._lgb = lgb
        self.model = lgb.LGBMClassifier(
            n_estimators=600,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=50,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            verbose=-1,
        )

    def fit(self, x: np.ndarray, y: np.ndarray, x_val: np.ndarray, y_val: np.ndarray) -> None:
        self.model.fit(
            x,
            y,
            eval_set=[(x_val, y_val)],
            eval_metric="binary_logloss",
            callbacks=[self._lgb.early_stopping(50, verbose=False)],
        )

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(x)[:, 1]  # type: ignore[no-any-return]

    def export(self) -> bytes:
        from onnxmltools import convert_lightgbm
        from onnxmltools.convert.common.data_types import FloatTensorType

        onnx_model = convert_lightgbm(
            self.model,
            initial_types=[("input", FloatTensorType([None, len(FEATURE_NAMES)]))],
            zipmap=False,
            target_opset=15,
        )
        return onnx_model.SerializeToString()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def load_frame(path: Path) -> pd.DataFrame:
    import pandas as pd

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix in (".jsonl", ".json"):
        df = pd.read_json(path, lines=path.suffix == ".jsonl")
    else:
        df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"training data is missing columns: {sorted(missing)}")
    return df


def _rolling_counts(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Sum of made and attempts per key over the HISTORY_DAYS before each service day."""
    daily = (
        df.groupby([*keys, "service_day"], as_index=False, dropna=False)
        .agg(made=("made", "sum"), n=("made", "size"))
        .sort_values("service_day")
    )
    rolled = (
        daily.set_index("service_day")
        .groupby(keys, dropna=False)[["made", "n"]]
        .rolling(f"{HISTORY_DAYS}D", closed="left")
        .sum()
        .reset_index()
        .fillna(0.0)
    )
    return rolled


def add_history(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time history: a row only sees outcomes from earlier days."""
    import pandas as pd

    df = df.copy()
    df["service_day"] = pd.to_datetime(df["service_day"]).dt.tz_localize(None).dt.normalize()
    df["made"] = df["made"].astype(int)

    exact = _rolling_counts(df, EXACT_KEYS).rename(columns={"made": "exact_made", "n": "exact_n"})
    group = _rolling_counts(df, GROUP_KEYS).rename(columns={"made": "group_made", "n": "group_n"})

    daily = df.groupby("service_day").agg(made=("made", "sum"), n=("made", "size")).sort_index()
    glob = daily.rolling(f"{HISTORY_DAYS}D", closed="left").sum().fillna(0.0)
    glob["global_rate"] = (glob["made"] / glob["n"]).where(glob["n"] > 0, DEFAULT_GLOBAL_RATE)

    out = df.merge(exact, on=[*EXACT_KEYS, "service_day"], how="left")
    out = out.merge(group, on=[*GROUP_KEYS, "service_day"], how="left")
    out = out.merge(glob[["global_rate"]], left_on="service_day", right_index=True, how="left")
    for col in ("exact_made", "exact_n", "group_made", "group_n"):
        out[col] = out[col].fillna(0.0)
    out["global_rate"] = out["global_rate"].fillna(DEFAULT_GLOBAL_RATE)
    return out


def build_matrix(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Feature matrix through the shared feature_vector(), the same code the API runs."""
    import numpy as np

    rows = [
        feature_vector(
            TransferInput(
                planned_buffer_min=int(r.planned_buffer_min),
                min_transfer_min=int(r.min_transfer_min),
                hour=int(r.hour),
                weekday=int(r.weekday),
                in_group=str(r.in_group),
                out_group=str(r.out_group),
            ),
            HistoryCounts(
                exact_made=float(r.exact_made),
                exact_n=float(r.exact_n),
                group_made=float(r.group_made),
                group_n=float(r.group_n),
                global_rate=float(r.global_rate),
            ),
        )
        for r in df.itertuples(index=False)
    ]
    x = np.asarray(rows, dtype=np.float32).reshape(-1, len(FEATURE_NAMES))
    return x, df["made"].to_numpy(dtype=np.int32)


@dataclass
class Split:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    weeks: list[str]


def split_by_week(df: pd.DataFrame, now: datetime) -> Split | None:
    """Weeks run Monday to Sunday. The current, unfinished week is left out."""
    import pandas as pd

    from .features import BERLIN

    current_week = str(pd.Timestamp(now.astimezone(BERLIN).date()).to_period("W-SUN"))
    weeks = df["service_day"].dt.to_period("W-SUN").astype(str)
    df, weeks = df[weeks < current_week], weeks[weeks < current_week]
    ordered = sorted(weeks.unique())
    if len(ordered) < MIN_WEEKS:
        return None
    test_week, val_week = ordered[-1], ordered[-2]
    return Split(
        train=df[weeks < val_week],
        val=df[weeks == val_week],
        test=df[weeks == test_week],
        weeks=ordered,
    )


# ---------------------------------------------------------------------------
# One training run
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    decision: Decision
    version: str | None
    challenger: Evaluation | None
    champion: Evaluation | None
    status: dict[str, Any]

    @property
    def exit_code(self) -> int:
        if self.decision.stage_dropped:
            return 3
        rejected = not self.decision.promote and self.champion is not None
        if rejected and "pinned" not in self.decision.reason:
            return 2
        return 0


def fit_isotonic(raw_val: np.ndarray, y_val: np.ndarray) -> Calibration:
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw_val, y_val)
    return Calibration(
        tuple(float(v) for v in iso.X_thresholds_), tuple(float(v) for v in iso.y_thresholds_)
    )


def _score_champion(
    registry: ModelRegistry,
    pointer: dict[str, Any] | None,
    x_test: np.ndarray,
    y_test: np.ndarray,
    baseline: Metrics,
    scorer_factory: ScorerFactory,
) -> Evaluation | None:
    if not pointer or not pointer.get("version"):
        return None
    version = pointer["version"]
    manifest = registry.read_json(version, "manifest.json") or {}
    if manifest.get("feature_version") != FEATURE_VERSION:
        log.warning("champion %s has other features; it cannot be compared", version)
        return None
    model_bytes = registry.read_file(version, "model.onnx")
    if model_bytes is None:
        log.warning("champion %s has no model file", version)
        return None
    scorer = scorer_factory(model_bytes)
    calibration = Calibration.from_json(registry.read_file(version, "calibration.json"))
    p = [calibration.apply(v) for v in scorer(x_test.tolist())]
    return Evaluation(evaluate(y_test.tolist(), p), baseline, int(manifest.get("weeks_of_data", 0)))


DEFAULT_CANDIDATES: tuple[Callable[[], TrainableModel], ...] = (LogisticModel, LightGBMModel)


def train_and_publish(
    df: pd.DataFrame,
    registry: ModelRegistry,
    candidates: Sequence[Callable[[], TrainableModel]] = DEFAULT_CANDIDATES,
    scorer_factory: ScorerFactory = onnx_scorer,
    now: datetime | None = None,
) -> RunResult:
    now = now or datetime.now(UTC)
    pointer = registry.current()
    previous_stage = Stage(pointer["stage"]) if pointer else None
    pinned = bool(pointer and pointer.get("pinned"))

    # No rows at all (the first days): nothing to compute, same path as too few weeks.
    split = None if df.empty else split_by_week(add_history(df), now)
    if split is None:
        decision = Decision(False, previous_stage or Stage.LIVE_ONLY, "fewer than 3 weeks of data")
        status = {"run_at": now.isoformat(), "decision": decision.reason, "stage": decision.stage}
        registry.write_status(status)
        if pointer is None:
            registry.set_current(None, Stage.LIVE_ONLY.value, reason=decision.reason)
        return RunResult(decision, None, None, None, status)

    x_tr, y_tr = build_matrix(split.train)
    x_val, y_val = build_matrix(split.val)
    x_te, y_te = build_matrix(split.test)

    # Model selection on the validation week; the test week stays unseen.
    fitted: list[tuple[float, TrainableModel]] = []
    for factory in candidates:
        candidate = factory()
        candidate.fit(x_tr, y_tr, x_val, y_val)
        val_brier = evaluate(y_val.tolist(), candidate.predict_proba(x_val).tolist()).brier
        log.info("%s: validation Brier %.4f", getattr(candidate, "kind", "model"), val_brier)
        fitted.append((val_brier, candidate))
    model = min(fitted, key=lambda pair: pair[0])[1]
    calibration = fit_isotonic(model.predict_proba(x_val), y_val)
    p_test = [calibration.apply(float(v)) for v in model.predict_proba(x_te)]

    exact_rate_col = FEATURE_NAMES.index("exact_rate")
    baseline = evaluate(y_te.tolist(), x_te[:, exact_rate_col].tolist())
    weeks_of_data = len(split.weeks) - 1  # the test week is not used for fitting
    challenger = Evaluation(evaluate(y_te.tolist(), p_test), baseline, weeks_of_data)
    champion = _score_champion(registry, pointer, x_te, y_te, baseline, scorer_factory)

    decision = decide(challenger, champion, previous_stage, pinned)

    version = new_version_id(now)
    manifest = {
        "version": version,
        "feature_version": FEATURE_VERSION,
        "features": list(FEATURE_NAMES),
        "model_type": getattr(model, "kind", type(model).__name__),
        "data_from": str(split.train["service_day"].min().date()),
        "data_to": str(split.val["service_day"].max().date()),
        "test_week": split.weeks[-1],
        "weeks_of_data": weeks_of_data,
        "rows": {"train": len(split.train), "val": len(split.val), "test": len(split.test)},
        "metrics": challenger.model.to_dict(),
        "baseline": baseline.to_dict(),
        "trained_at": now.isoformat(),
    }
    registry.save_version(
        version,
        {
            "model.onnx": model.export(),
            "calibration.json": json.dumps({"x": calibration.x, "y": calibration.y}).encode(),
            "manifest.json": json.dumps(manifest, indent=2).encode(),
        },
    )

    status = {
        "run_at": now.isoformat(),
        "challenger_version": version,
        "champion_version": pointer.get("version") if pointer else None,
        "promoted": decision.promote,
        "model_type": getattr(model, "kind", type(model).__name__),
        "stage": decision.stage.value,
        "stage_dropped": decision.stage_dropped,
        "decision": decision.reason,
        "challenger": challenger.model.to_dict(),
        "champion": champion.model.to_dict() if champion else None,
        "baseline": baseline.to_dict(),
        "weeks_of_data": weeks_of_data,
    }
    registry.write_status(status)

    # Last write of the run: the pointer the API trusts.
    live_version = version if decision.promote else (pointer or {}).get("version")
    registry.set_current(live_version, decision.stage.value, pinned=pinned, reason=decision.reason)
    return RunResult(decision, version, challenger, champion, status)


def summary_markdown(result: RunResult) -> str:
    s = result.status
    lines = [
        "## Weekly retrain",
        "",
        f"**Decision:** {s.get('decision')}  ",
        f"**Stage:** `{s.get('stage')}`  ",
        f"**Weeks of data:** {s.get('weeks_of_data', '-')}  ",
        f"**Model type:** {s.get('model_type', '-')}",
        "",
    ]
    if result.challenger:
        lines += [
            "| Model | ROC AUC | Brier | Calibration error | Test rows |",
            "| --- | --- | --- | --- | --- |",
        ]
        rows = [("Challenger", result.challenger.model), ("Baseline A", result.challenger.baseline)]
        if result.champion:
            rows.insert(1, ("Champion", result.champion.model))
        for name, m in rows:
            lines.append(
                f"| {name} | {m.auc:.3f} | {m.brier:.4f} | {m.calibration_error:.3f} | {m.n} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anschlussradar-train")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--store", choices=["local", "blob"], default="local")
    parser.add_argument("--local-root", type=Path, default=Path("data/models"))
    parser.add_argument("--blob-account-url", default=os.environ.get("MODELS_ACCOUNT_URL", ""))
    parser.add_argument("--container", default="models")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.store == "blob":
        if not args.blob_account_url:
            parser.error("--blob-account-url or MODELS_ACCOUNT_URL is required for --store blob")
        store: Any = BlobStore(args.blob_account_url, args.container)
    else:
        store = LocalStore(args.local_root)

    result = train_and_publish(load_frame(args.data), ModelRegistry(store))
    summary = summary_markdown(result)
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(summary)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())

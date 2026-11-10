"""Full weekly runs on synthetic data, with a scikit-learn model in place of LightGBM."""

import json
import math
import pickle
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from anschlussradar.ml.features import buffer_bucket, min_transfer_minutes  # noqa: E402
from anschlussradar.ml.registry import LocalStore, ModelRegistry  # noqa: E402
from anschlussradar.ml.stages import Stage  # noqa: E402
from anschlussradar.ml.train import add_history, train_and_publish  # noqa: E402

NOW = datetime(2026, 11, 30, 2, 17, tzinfo=UTC)  # Monday night run


def synthetic(weeks: int, hubs: int = 5, pairs: int = 40, seed: int = 7) -> pd.DataFrame:
    """Daily transfers per hub. Success depends on slack, a hidden pair effect and the weekday.

    A third of the transfers only start in the last three weeks (like after a timetable
    change), so the history baseline has little to go on there and the model must
    generalise from slack, train types and weekday.
    """
    rng = random.Random(seed)
    cats = [("S", "sbahn"), ("RE", "regional"), ("ICE", "long")]
    templates = []
    for h in range(hubs):
        for p in range(pairs):
            in_cat, in_group = rng.choice(cats)
            out_cat, out_group = rng.choice(cats)
            min_t = min_transfer_minutes(in_cat, out_cat)
            templates.append(
                {
                    "eva": 8000000 + h,
                    "in_number": f"{h}{p}1",
                    "out_number": f"{h}{p}2",
                    "in_category": in_cat,
                    "out_category": out_cat,
                    "in_group": in_group,
                    "out_group": out_group,
                    "planned_buffer_min": rng.randint(min_t, 20),
                    "min_transfer_min": min_t,
                    "hour": rng.randint(5, 22),
                    "effect": rng.gauss(0, 0.8),
                    "starts": 0 if p % 3 else 7 * (weeks - 3),
                }
            )
    last_sunday = date(2026, 11, 29)
    start = last_sunday - timedelta(days=7 * weeks - 1)
    rows = []
    for d in range(7 * weeks):
        day = start + timedelta(days=d)
        weekend = day.weekday() >= 5
        for t in templates:
            if d < t["starts"]:
                continue
            slack = t["planned_buffer_min"] - t["min_transfer_min"]
            p = 1 / (1 + math.exp(-(-1.0 + 0.35 * slack + t["effect"] + (1.5 if weekend else 0.0))))
            rows.append(
                {
                    **{k: v for k, v in t.items() if k not in ("effect", "starts")},
                    "service_day": pd.Timestamp(day),
                    "buffer_bucket": buffer_bucket(t["planned_buffer_min"]),
                    "weekday": (day.weekday() + 1) % 7,
                    "made": rng.random() < p,
                }
            )
    return pd.DataFrame(rows)


class SkModel:
    def __init__(self) -> None:
        from sklearn.ensemble import HistGradientBoostingClassifier

        self.model = HistGradientBoostingClassifier(max_iter=80, random_state=0)

    def fit(self, x, y, x_val, y_val):  # type: ignore[no-untyped-def]
        self.model.fit(x, y)

    def predict_proba(self, x):  # type: ignore[no-untyped-def]
        return self.model.predict_proba(x)[:, 1]

    def export(self) -> bytes:
        return pickle.dumps(self.model)


class SkLogistic(SkModel):
    def __init__(self) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self.model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))


CANDIDATES = (SkLogistic, SkModel)


class _Constant:
    def predict_proba(self, x):  # type: ignore[no-untyped-def]
        return np.column_stack([np.full(len(x), 0.5), np.full(len(x), 0.5)])


class ConstantModel:
    def fit(self, *args):  # type: ignore[no-untyped-def]
        pass

    def predict_proba(self, x):  # type: ignore[no-untyped-def]
        return np.full(len(x), 0.5)

    def export(self) -> bytes:
        return pickle.dumps(_Constant())


def pickle_scorer(model_bytes: bytes):  # type: ignore[no-untyped-def]
    model = pickle.loads(model_bytes)  # test only; production uses ONNX
    return lambda rows: model.predict_proba(np.asarray(rows, dtype=np.float32))[:, 1].tolist()


def test_history_is_point_in_time() -> None:
    df = pd.DataFrame(
        {
            "service_day": pd.to_datetime(["2026-11-02", "2026-11-02", "2026-11-03"]),
            "eva": [1, 1, 1],
            "in_number": ["a", "a", "a"],
            "out_number": ["b", "b", "b"],
            "in_group": ["sbahn"] * 3,
            "out_group": ["long"] * 3,
            "buffer_bucket": ["07-09"] * 3,
            "made": [True, False, True],
        }
    )
    out = add_history(df).sort_values("service_day")
    first_day = out[out["service_day"] == "2026-11-02"]
    second_day = out[out["service_day"] == "2026-11-03"].iloc[0]
    assert (first_day["exact_n"] == 0).all()  # same-day outcomes are not visible
    assert second_day["exact_n"] == 2 and second_day["exact_made"] == 1


def test_too_little_data_stays_live_only(tmp_path: Path) -> None:
    reg = ModelRegistry(LocalStore(tmp_path))
    result = train_and_publish(synthetic(weeks=2), reg, CANDIDATES, pickle_scorer, now=NOW)
    assert not result.decision.promote
    assert reg.current() is not None and reg.current()["stage"] == "live_only"
    assert result.exit_code == 0


def test_weekly_cycle_promote_keep_reject(tmp_path: Path) -> None:
    reg = ModelRegistry(LocalStore(tmp_path))
    data = synthetic(weeks=8)

    # Week 1: no champion yet, a good first model goes live.
    first = train_and_publish(data, reg, CANDIDATES, pickle_scorer, now=NOW)
    assert first.decision.promote, first.decision.reason
    assert first.decision.stage in (Stage.EARLY, Stage.FULL)
    assert first.challenger is not None and first.challenger.model.auc > first.challenger.baseline.auc
    assert reg.current()["version"] == first.version
    manifest = reg.read_json(first.version, "manifest.json")
    assert manifest["test_week"].startswith("2026-11-23")
    assert manifest["weeks_of_data"] == 7

    # Week 2: the same kind of model is as good as the champion, so it is promoted.
    second = train_and_publish(data, reg, CANDIDATES, pickle_scorer, now=NOW + timedelta(seconds=1))
    assert second.champion is not None
    assert second.decision.promote, second.decision.reason
    assert reg.current()["version"] == second.version

    # Week 3: a useless model is rejected; the champion stays live and the job fails.
    third = train_and_publish(data, reg, (ConstantModel,), pickle_scorer, now=NOW + timedelta(seconds=2))
    assert not third.decision.promote
    assert reg.current()["version"] == second.version
    assert third.exit_code == 2
    status = json.loads((tmp_path / "transfer" / "status.json").read_text())
    assert status["promoted"] is False and status["challenger_version"] == third.version


def test_unfinished_current_week_is_ignored(tmp_path: Path) -> None:
    data = synthetic(weeks=8)
    monday_rows = data[data["service_day"] == data["service_day"].max()].copy()
    monday_rows["service_day"] = pd.Timestamp("2026-11-30")
    with_partial = pd.concat([data, monday_rows])
    result = train_and_publish(with_partial, ModelRegistry(LocalStore(tmp_path)), CANDIDATES, pickle_scorer, now=NOW)
    assert result.status["weeks_of_data"] == 7

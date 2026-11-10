from datetime import UTC, datetime

import pytest

from anschlussradar.ml.features import (
    FEATURE_NAMES,
    HistoryCounts,
    TransferInput,
    buffer_bucket,
    category_group,
    confidence_label,
    feature_vector,
    kql_weekday,
    min_transfer_minutes,
    shrunk_rates,
)


@pytest.mark.parametrize(
    ("category", "group"),
    [
        ("ICE", "long"),
        ("ic", "long"),
        (" RE ", "regional"),
        ("S", "sbahn"),
        ("BUS", "other"),
        (None, "other"),
    ],
)
def test_category_group(category: str | None, group: str) -> None:
    assert category_group(category) == group


def test_min_transfer_is_longer_for_long_distance() -> None:
    assert min_transfer_minutes("S", "ICE") == 5
    assert min_transfer_minutes("S", "RE") == 3


@pytest.mark.parametrize(
    ("minutes", "label"),
    [(3, "03-04"), (6, "05-06"), (12, "10-14"), (30, "15-30"), (31, "outside")],
)
def test_buffer_bucket(minutes: int, label: str) -> None:
    assert buffer_bucket(minutes) == label


def test_few_observations_stay_close_to_the_group() -> None:
    group_rate, exact_rate = shrunk_rates(
        HistoryCounts(exact_made=0, exact_n=2, group_made=900, group_n=1000, global_rate=0.8)
    )
    assert group_rate == pytest.approx(0.898, abs=0.005)
    assert exact_rate > 0.7  # two misses do not make it look hopeless


def test_many_observations_follow_their_own_record() -> None:
    _, exact_rate = shrunk_rates(
        HistoryCounts(exact_made=50, exact_n=200, group_made=900, group_n=1000, global_rate=0.8)
    )
    assert exact_rate < 0.35


def test_no_history_falls_back_to_global_rate() -> None:
    group_rate, exact_rate = shrunk_rates(HistoryCounts(global_rate=0.77))
    assert group_rate == pytest.approx(0.77)
    assert exact_rate == pytest.approx(0.77)


def test_feature_vector_shape_and_values() -> None:
    t = TransferInput(
        planned_buffer_min=8,
        min_transfer_min=5,
        hour=7,
        weekday=1,
        in_group="sbahn",
        out_group="long",
    )
    v = feature_vector(t, HistoryCounts())
    assert len(v) == len(FEATURE_NAMES)
    named = dict(zip(FEATURE_NAMES, v, strict=True))
    assert named["slack_min"] == 3
    assert named["in_sbahn"] == 1 and named["out_long"] == 1 and named["in_long"] == 0
    assert named["is_weekend"] == 0


def test_transfer_input_from_trains_uses_german_time() -> None:
    # 06:48 UTC on Wednesday 4 Nov 2026 is 07:48 in Germany
    t = TransferInput.from_trains(
        datetime(2026, 11, 4, 6, 48, tzinfo=UTC),
        datetime(2026, 11, 4, 6, 56, tzinfo=UTC),
        "S",
        "ICE",
    )
    assert (t.planned_buffer_min, t.min_transfer_min, t.hour, t.weekday) == (8, 5, 7, 3)


def test_kql_weekday_sunday_is_zero() -> None:
    assert kql_weekday(datetime(2026, 11, 8, 12, 0, tzinfo=UTC)) == 0


@pytest.mark.parametrize(
    ("n", "label"), [(0, "limited"), (9, "limited"), (10, "medium"), (49, "medium"), (50, "high")]
)
def test_confidence_label(n: int, label: str) -> None:
    assert confidence_label(n) == label

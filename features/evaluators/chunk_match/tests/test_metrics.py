"""Tests for query_index_eval.metrics.

Each metric tested with single-relevant, multi-relevant, edge cases (empty
expected, empty retrieved, all-miss, all-hit, partial-hit), and order
sensitivity where relevant.
"""

from __future__ import annotations

import pytest

# ---------- recall_at_k ----------


@pytest.mark.parametrize(
    "expected,retrieved,k,want",
    [
        ({"a"}, ["a"], 1, 1.0),
        ({"a"}, ["b"], 1, 0.0),
        ({"a"}, ["b", "a"], 2, 1.0),
        ({"a"}, ["b", "a"], 1, 0.0),
        ({"a", "b"}, ["a", "c"], 2, 0.5),
        ({"a", "b"}, ["a", "b", "c"], 3, 1.0),
        ({"a", "b", "c"}, ["d", "e", "f"], 3, 0.0),
        (set(), [], 5, 0.0),
        (set(), ["a"], 5, 0.0),
        ({"a"}, [], 5, 0.0),
    ],
)
def test_recall_at_k(expected, retrieved, k, want) -> None:
    from query_index_eval.metrics import recall_at_k

    assert recall_at_k(expected, retrieved, k) == pytest.approx(want)


# ---------- hit_rate_at_k ----------


@pytest.mark.parametrize(
    "expected,retrieved,k,want",
    [
        ({"a"}, ["a"], 1, 1.0),
        ({"a"}, ["b"], 1, 0.0),
        ({"a"}, ["b", "a"], 2, 1.0),
        ({"a", "b"}, ["a", "c"], 2, 1.0),
        ({"a", "b"}, ["c", "d"], 2, 0.0),
        (set(), ["a"], 5, 0.0),
        ({"a"}, [], 5, 0.0),
    ],
)
def test_hit_rate_at_k(expected, retrieved, k, want) -> None:
    from query_index_eval.metrics import hit_rate_at_k

    assert hit_rate_at_k(expected, retrieved, k) == pytest.approx(want)


# ---------- MRR ----------


@pytest.mark.parametrize(
    "expected,retrieved,want",
    [
        ({"a"}, ["a"], 1.0),
        ({"a"}, ["b", "a"], 0.5),
        ({"a"}, ["b", "c", "a"], 1 / 3),
        ({"a", "b"}, ["b", "a"], 1.0),
        ({"a", "b"}, ["c", "a", "b"], 0.5),
        ({"a"}, ["b", "c", "d"], 0.0),
        (set(), ["a"], 0.0),
    ],
)
def test_mrr(expected, retrieved, want) -> None:
    from query_index_eval.metrics import mrr

    assert mrr(expected, retrieved) == pytest.approx(want)


# ---------- Average Precision ----------


def test_average_precision_single_relevant_at_top() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision({"a"}, ["a", "b", "c"]) == pytest.approx(1.0)


def test_average_precision_single_relevant_at_rank_3() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision({"a"}, ["b", "c", "a"]) == pytest.approx(1 / 3)


def test_average_precision_two_relevant_well_ranked() -> None:
    from query_index_eval.metrics import average_precision

    # rank 1: precision = 1/1; rank 2: precision = 2/2; mean = (1 + 1) / 2 = 1.0
    assert average_precision({"a", "b"}, ["a", "b", "c"]) == pytest.approx(1.0)


def test_average_precision_two_relevant_with_gap() -> None:
    from query_index_eval.metrics import average_precision

    # rank 1: precision = 1/1; rank 3: precision = 2/3; mean = (1 + 2/3) / 2 = 5/6
    assert average_precision({"a", "b"}, ["a", "x", "b"]) == pytest.approx(5 / 6)


def test_average_precision_zero_when_no_hit() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision({"a"}, ["b", "c"]) == 0.0


def test_average_precision_zero_when_expected_empty() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision(set(), ["a"]) == 0.0


# ---------- mean_average_precision ----------


def test_mean_average_precision_averages_per_query_ap() -> None:
    from query_index_eval.metrics import mean_average_precision

    pairs = [
        ({"a"}, ["a", "b"]),  # AP = 1.0
        ({"x"}, ["y", "x"]),  # AP = 1/2
        ({"q"}, ["w", "e", "r"]),  # AP = 0.0
    ]
    assert mean_average_precision(pairs) == pytest.approx(0.5)


def test_mean_average_precision_empty_input_is_zero() -> None:
    from query_index_eval.metrics import mean_average_precision

    assert mean_average_precision([]) == 0.0

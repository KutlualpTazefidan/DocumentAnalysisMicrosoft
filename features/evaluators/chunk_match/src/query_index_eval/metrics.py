"""Pure IR metric functions over (expected, retrieved) chunk-id collections.

No I/O, no Azure, no global state. Every function accepts a `set[str]` of
expected chunk_ids and a `list[str]` of retrieved chunk_ids in rank order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def recall_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 0.0
    top_k = set(retrieved[:k])
    return len(expected & top_k) / len(expected)


def hit_rate_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 0.0
    top_k = set(retrieved[:k])
    return 1.0 if expected & top_k else 0.0


def mrr(expected: set[str], retrieved: list[str]) -> float:
    if not expected:
        return 0.0
    for i, item in enumerate(retrieved, start=1):
        if item in expected:
            return 1.0 / i
    return 0.0


def average_precision(expected: set[str], retrieved: list[str]) -> float:
    """Precision averaged at the ranks where each relevant item appears.

    AP = (1 / |expected|) * sum over k where retrieved[k-1] is relevant
          of (number-of-hits-up-to-k / k)
    """
    if not expected:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for i, item in enumerate(retrieved, start=1):
        if item in expected:
            hits += 1
            precision_sum += hits / i
    return precision_sum / len(expected) if precision_sum else 0.0


def mean_average_precision(
    pairs: Iterable[tuple[set[str], list[str]]],
) -> float:
    pair_list = list(pairs)
    if not pair_list:
        return 0.0
    return sum(average_precision(e, r) for e, r in pair_list) / len(pair_list)

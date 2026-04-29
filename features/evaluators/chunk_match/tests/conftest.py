"""Shared fixtures for query_index_eval tests.

The `query_index` package is patched at module level so that no test in this
suite ever touches Azure. Fixtures expose: a make_entry factory for
RetrievalEntry construction.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from goldens import RetrievalEntry, new_entry_id


@pytest.fixture(autouse=True)
def _patch_get_chunk():
    """Prevent any test from calling the real get_chunk (which hits Azure).

    Tests that need specific get_chunk behaviour override this by adding their
    own ``patch("query_index_eval.runner.get_chunk", ...)`` context manager,
    which takes precedence over this autouse patch.
    """
    with patch("query_index_eval.runner.get_chunk", return_value=MagicMock(chunk="")):
        yield


@pytest.fixture
def make_entry():
    """Factory for RetrievalEntry test instances. review_chain=() yields
    level='synthetic' (legal — see schemas.retrieval._highest_level)."""

    def _make(
        entry_id: str | None = None,
        query: str = "Q?",
        expected: tuple[str, ...] = ("c1",),
        chunk_hashes: dict[str, str] | None = None,
        deprecated: bool = False,
    ) -> RetrievalEntry:
        return RetrievalEntry(
            entry_id=entry_id or new_entry_id(),
            query=query,
            expected_chunk_ids=expected,
            chunk_hashes=chunk_hashes or {c: f"sha256:{c}" for c in expected},
            review_chain=(),
            deprecated=deprecated,
        )

    return _make

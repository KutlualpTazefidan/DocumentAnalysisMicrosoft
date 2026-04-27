"""Tests for query_index_eval.curate.

Most of curate's surface is interactive, so we test the pure-logic helpers
plus the substring check in isolation. The interactive run loop is exercised
manually by the user, not unit-tested end-to-end.
"""

from __future__ import annotations

import pytest


def test_query_substring_check_flags_long_overlap() -> None:
    from query_index_eval.curate import query_substring_overlap

    chunk = "Der Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020."
    leaky_query = "Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020"
    assert query_substring_overlap(leaky_query, chunk) >= 30


def test_query_substring_check_passes_short_keyword_overlap() -> None:
    from query_index_eval.curate import query_substring_overlap

    chunk = "Der Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020."
    safe_query = "Wo steht der Tragkorbdurchmesser?"
    # Overlap "Tragkorbdurchmesser" is 19 chars — below the 30-char heuristic
    assert query_substring_overlap(safe_query, chunk) < 30


def test_query_substring_check_zero_when_disjoint() -> None:
    from query_index_eval.curate import query_substring_overlap

    assert query_substring_overlap("etwas anderes", "Tragkorb") == 0


def test_require_tty_raises_when_stdin_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from query_index_eval.curate import require_interactive_tty

    monkeypatch.setattr("os.isatty", lambda _fd: False)
    with pytest.raises(SystemExit) as excinfo:
        require_interactive_tty()
    assert excinfo.value.code == 1


def test_require_tty_passes_when_stdin_is_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from query_index_eval.curate import require_interactive_tty

    monkeypatch.setattr("os.isatty", lambda _fd: True)
    require_interactive_tty()  # should not raise

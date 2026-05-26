"""Tests for the pseudonym generator + validator."""

from __future__ import annotations

import pytest
from local_pdf.auth.pseudonyms import (
    generate_pseudonym,
    validate_user_pseudonym,
)


def test_generate_pseudonym_shape() -> None:
    p = generate_pseudonym()
    assert " " in p  # "Adjective Animal"
    assert p[0].isupper()


def test_generate_pseudonym_avoids_excluded() -> None:
    """The generator must not return an excluded value (modulo
    astronomical luck via the suffix fallback)."""
    # Exclude a single known value; with 25*25 possible pairs there's
    # no realistic chance of needing the fallback to dodge ONE name.
    seen = {"Wachsamer Hirsch"}
    for _ in range(20):
        assert generate_pseudonym(exclude=seen) != "Wachsamer Hirsch"


def test_generate_pseudonym_with_full_exhaustion_uses_suffix() -> None:
    """When every base pair is excluded, the generator falls back to
    suffixed form '... NN'."""
    # Build an exclusion set the size of the cartesian product so
    # max_tries always misses; the fallback path runs.
    from local_pdf.auth.pseudonyms import _ADJECTIVES, _ANIMALS

    full = {f"{a} {n}" for a in _ADJECTIVES for n in _ANIMALS}
    result = generate_pseudonym(exclude=full, max_tries=5)
    # Suffix has 2-digit decimal; the result is either still a base
    # pair (caught one of the 5 max_tries against the full set — but
    # we excluded ALL bases, so impossible) or has a numeric suffix.
    assert result.split()[-1].isdigit()


def test_validate_rejects_empty() -> None:
    with pytest.raises(ValueError, match="leer"):
        validate_user_pseudonym("")
    with pytest.raises(ValueError, match="leer"):
        validate_user_pseudonym("   ")


def test_validate_rejects_too_short() -> None:
    with pytest.raises(ValueError, match="mindestens"):
        validate_user_pseudonym("ab")


def test_validate_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="hoechstens"):
        validate_user_pseudonym("x" * 100)


def test_validate_rejects_email() -> None:
    with pytest.raises(ValueError, match="E-Mail"):
        validate_user_pseudonym("kutlu@example.com")
    with pytest.raises(ValueError, match="E-Mail"):
        validate_user_pseudonym("My pseudonym is foo@bar.de actually")


def test_validate_rejects_realname_first_token() -> None:
    """Pseudonyms whose FIRST token matches a common German given name
    are rejected as obvious de-anonymisation. The list is small and
    case-insensitive."""
    with pytest.raises(ValueError, match="realer Vorname"):
        validate_user_pseudonym("Hans Müller")
    with pytest.raises(ValueError, match="realer Vorname"):
        validate_user_pseudonym("Anna Schmidt")
    with pytest.raises(ValueError, match="realer Vorname"):
        validate_user_pseudonym("Klaus")
    # Capitalisation-insensitive:
    with pytest.raises(ValueError, match="realer Vorname"):
        validate_user_pseudonym("monika foo")


def test_validate_accepts_legitimate_pseudonym() -> None:
    assert validate_user_pseudonym("Wachsamer Hirsch") == "Wachsamer Hirsch"
    assert validate_user_pseudonym("anon42") == "anon42"
    # Multi-word non-realname patterns are fine.
    assert validate_user_pseudonym("Reviewer der Bewertungen") == "Reviewer der Bewertungen"


def test_validate_strips_whitespace() -> None:
    assert validate_user_pseudonym("  Stiller Wolf  ") == "Stiller Wolf"

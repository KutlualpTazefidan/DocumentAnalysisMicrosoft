"""Tests for the deterministic Calculator helpers used by evaluate."""

from __future__ import annotations

from local_pdf.provenienz.calculator import (
    Quantity,
    best_pairwise_compare,
    compare,
    parse_quantities,
    sum_quantities,
)


def test_parse_quantities_german_decimal_comma():
    qs = parse_quantities("Die Anlage hat 5,597 kW.")
    assert len(qs) == 1
    assert qs[0].raw_unit == "kW"
    # 5,597 kW = 5597 W canonical
    assert abs(qs[0].value - 5597.0) < 1e-6
    assert qs[0].unit == "W"


def test_parse_quantities_english_decimal_point():
    qs = parse_quantities("Total output: 5.597 MW.")
    assert len(qs) == 1
    assert qs[0].raw_unit == "MW"
    assert abs(qs[0].value - 5.597e6) < 1e-3


def test_parse_quantities_multiple_units():
    qs = parse_quantities("Druck 2,5 MPa und Temperatur 350 K.")
    raw_units = [q.raw_unit for q in qs]
    assert "MPa" in raw_units
    assert "K" in raw_units


def test_parse_quantities_celsius_to_kelvin():
    qs = parse_quantities("Außentemperatur 20 °C.")
    assert len(qs) == 1
    assert qs[0].raw_unit == "°C"
    assert qs[0].unit == "K"
    assert abs(qs[0].value - 293.15) < 1e-6


def test_parse_quantities_thousand_space_separator():
    qs = parse_quantities("Energie 12 500 kWh über die Kampagne.")
    assert len(qs) == 1
    assert abs(qs[0].value - 12500e3) < 1e-3  # 12.5 MWh in Wh


def test_parse_quantities_skips_unknown_units():
    qs = parse_quantities("Es kostet 50 EUR und braucht 3 Stunden.")
    assert qs == []


def test_compare_strict_equal_default():
    """Default: no tolerance. Only EXACT canonical equality counts as
    'equal'. Any non-zero difference is 'different', regardless of how
    small."""
    a = Quantity(value=5597.0, unit="W", raw_unit="kW")
    b = Quantity(value=5597.0, unit="W", raw_unit="kW")
    out = compare(a, b)  # rel_tolerance=0 default
    assert out["kind"] == "equal"
    assert out["match"] is True


def test_compare_near_miss_is_different_under_strict_default():
    """5597 vs 5600 W — close, but NOT exact. Strict default (no
    tolerance) reports 'different'. The 0.054% deviation is a fact for
    Skills/LLM to interpret, not a tool-level pass."""
    a = Quantity(value=5597.0, unit="W", raw_unit="kW")
    b = Quantity(value=5600.0, unit="W", raw_unit="kW")
    out = compare(a, b)
    assert out["kind"] == "different"
    assert out["match"] is False
    assert out["rel_diff"] > 0


def test_compare_near_miss_passes_when_tolerance_explicitly_supplied():
    """Caller can opt into tolerance-based matching by passing
    rel_tolerance > 0 (used by domain skills, NOT by default)."""
    a = Quantity(value=5597.0, unit="W", raw_unit="kW")
    b = Quantity(value=5600.0, unit="W", raw_unit="kW")
    out = compare(a, b, rel_tolerance=0.01)
    assert out["match"] is True


def test_compare_far_miss_different():
    a = Quantity(value=5597.0, unit="W", raw_unit="kW")
    b = Quantity(value=7200.0, unit="W", raw_unit="kW")
    out = compare(a, b, rel_tolerance=0.01)
    assert out["match"] is False
    assert out["kind"] == "different"


def test_compare_unit_mismatch():
    a = Quantity(value=5597.0, unit="W", raw_unit="kW")
    b = Quantity(value=5.6e6, unit="Pa", raw_unit="MPa")
    out = compare(a, b)
    assert out["match"] is False
    assert out["kind"] == "unit-mismatch"


def test_compare_cross_prefix_normalised():
    """5,597 kW vs 5597 W must compare as exact-equal — the canonical
    representation (W) is identical, no tolerance needed."""
    a = parse_quantities("5,597 kW")[0]
    b = parse_quantities("5597 W")[0]
    out = compare(a, b)
    assert out["match"] is True
    assert out["kind"] == "equal"


def test_sum_same_unit():
    qs = [
        Quantity(value=5597.0, unit="W", raw_unit="kW"),
        Quantity(value=2100.0, unit="W", raw_unit="kW"),
    ]
    out = sum_quantities(qs)
    assert out["ok"] is True
    assert abs(out["total"] - 7697.0) < 1e-6
    assert out["unit"] == "W"


def test_sum_unit_mismatch():
    qs = [
        Quantity(value=5597.0, unit="W", raw_unit="kW"),
        Quantity(value=5.6e6, unit="Pa", raw_unit="MPa"),
    ]
    out = sum_quantities(qs)
    assert out["ok"] is False
    assert "MPa" in out["raw_units"]


def test_sum_empty_input():
    assert sum_quantities([])["ok"] is False


def test_best_pairwise_strict_default_only_exact():
    """Default rel_tolerance=0 — only exact equals count as match.
    A close-but-not-exact pair gets 'no match', closest result still
    surfaces the rel_diff for downstream reasoning."""
    a_qs = parse_quantities("Wärmeleistung 5,597 kW")
    b_qs = parse_quantities("Tabellenwert 5,5 kW; weitere Werte 2,1 kW.")
    out = best_pairwise_compare(a_qs, b_qs)
    # No pair is EXACTLY 5597 W → any_match=False
    assert out["any_match"] is False
    assert out["closest"]["rel_diff"] > 0


def test_best_pairwise_match_with_explicit_tolerance():
    """Explicit tolerance lets a near-miss count as match — but the
    caller has to opt in (no implicit default)."""
    a_qs = parse_quantities("Wärmeleistung 5,597 kW")
    b_qs = parse_quantities("Tabellenwert 5,5 kW")
    out = best_pairwise_compare(a_qs, b_qs, rel_tolerance=0.05)
    # With 5% tolerance, 5.597 vs 5.5 → ~1.75% → match.
    assert out["any_match"] is True
    # match flag set, but kind stays "different" (not exact).
    assert out["closest"]["match"] is True
    assert out["closest"]["kind"] == "different"


def test_best_pairwise_no_match():
    a_qs = parse_quantities("Wärmeleistung 5,597 kW")
    b_qs = parse_quantities("Druck 7,2 MPa.")
    out = best_pairwise_compare(a_qs, b_qs)
    assert out["any_match"] is False
    # Closest result IS unit-mismatch (kW vs MPa).
    assert out["closest"]["kind"] == "unit-mismatch"


def test_best_pairwise_no_quantities_in_one_side():
    out = best_pairwise_compare([], parse_quantities("5 kW"))
    assert out["ok"] is False

"""Deterministic numerical-comparison helpers for the Calculator tool.

The LLM-driven evaluate step often needs to decide whether two
quantities (e.g. "5,597 kW" in the claim vs "5,5 kW" in a candidate)
match. LLMs handle this unreliably — they parse decimal commas wrong,
forget unit prefixes, hallucinate rounding rules. This module pulls
the math out of the LLM:

  parse_quantities(text)     → list[Quantity]   (value normalised to base)
  compare(a, b, tolerance)   → dict             (deterministic match flag)
  sum_quantities(qs)         → dict             (total in base unit)

Used by the /calculator endpoint, which the evaluate route calls
inline so the LLM gets a verified comparison result alongside the
raw texts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Quantity:
    """A parsed (number, unit) pair, value normalised to the unit's
    SI-base. ``raw_unit`` keeps what the original text used so the
    caller can echo back the user-visible form.
    """

    value: float
    unit: str  # base unit — "W", "Pa", "K", "kg", "m", "J", "Wh"
    raw_unit: str


# Conversion factors to a canonical base per dimension. Keep extending
# as new domains show up.
_FACTORS: dict[str, dict[str, float]] = {
    "W": {"W": 1.0, "kW": 1e3, "MW": 1e6, "GW": 1e9},
    "Pa": {
        "Pa": 1.0,
        "kPa": 1e3,
        "MPa": 1e6,
        "GPa": 1e9,
        "bar": 1e5,
        "mbar": 1e2,
    },
    "K": {"K": 1.0},  # °C / °F handled below as offset conversions
    "kg": {"g": 1e-3, "kg": 1.0, "t": 1e3, "Mg": 1e3},
    "m": {"mm": 1e-3, "cm": 1e-2, "m": 1.0, "km": 1e3},
    "J": {"J": 1.0, "kJ": 1e3, "MJ": 1e6, "GJ": 1e9},
    "Wh": {"Wh": 1.0, "kWh": 1e3, "MWh": 1e6, "GWh": 1e9},
}

_UNIT_TO_BASE: dict[str, str] = {u: base for base, m in _FACTORS.items() for u in m}

# Number + unit regex. Order multi-char units before their prefixes
# (kWh before kW, °C before K, MPa before Pa) so the longest match
# wins. The number sub-pattern accepts German decimal comma and
# space-thousand-separator.
_NUMBER_UNIT_RE = re.compile(
    r"(?P<num>-?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?)"
    r"\s*"
    r"(?P<unit>"
    r"°C|°F|"
    r"kWh|MWh|GWh|"
    r"kJ|MJ|GJ|"
    r"kW|MW|GW|"
    r"kPa|MPa|GPa|mbar|"
    r"mm|cm|km|"
    r"W|J|Pa|bar|K|Mg|kg|"
    r"\bt\b|\bg\b|\bm\b"
    r")",
    re.UNICODE,
)


def _coerce_number(raw: str) -> float | None:
    """Parse a number string allowing German conventions.

    Rules: if both '.' and ',' appear, the last one is the decimal
    separator. If only ',' appears, treat it as decimal. Spaces are
    stripped (thousand separators).
    """
    s = raw.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_quantities(text: str) -> list[Quantity]:
    """Extract every (number, known-unit) pair from *text*. Values are
    normalised to the unit's base (e.g. ``5.597 kW`` → ``5597.0 W``).
    Unknown units are skipped silently. ``°C`` / ``°F`` parse but stay
    in their own offset-keyed dimension — caller decides whether to
    fold to Kelvin.
    """
    out: list[Quantity] = []
    for m in _NUMBER_UNIT_RE.finditer(text):
        value = _coerce_number(m.group("num"))
        if value is None:
            continue
        raw_unit = m.group("unit")
        if raw_unit == "°C":
            out.append(Quantity(value=value + 273.15, unit="K", raw_unit="°C"))
            continue
        if raw_unit == "°F":
            out.append(Quantity(value=(value - 32) * 5 / 9 + 273.15, unit="K", raw_unit="°F"))
            continue
        base = _UNIT_TO_BASE.get(raw_unit)
        if base is None:
            continue
        canonical = value * _FACTORS[base][raw_unit]
        out.append(Quantity(value=canonical, unit=base, raw_unit=raw_unit))
    return out


def compare(a: Quantity, b: Quantity, *, rel_tolerance: float = 0.01) -> dict[str, Any]:
    """Compare two quantities deterministically.

    Returns a dict with:
      match (bool), kind ("equal" | "different" | "unit-mismatch"),
      a / b  (value+unit echoed),
      rel_diff / abs_diff,
      reasoning (German one-liner).

    ``rel_tolerance`` is fractional (0.01 = 1 %). Symmetric against
    sign — a == -a is False.
    """
    if a.unit != b.unit:
        return {
            "match": False,
            "kind": "unit-mismatch",
            "a": {"value": a.value, "unit": a.unit, "raw_unit": a.raw_unit},
            "b": {"value": b.value, "unit": b.unit, "raw_unit": b.raw_unit},
            "reasoning": (
                f"Unterschiedliche Einheits-Dimensionen: {a.raw_unit} ({a.unit}) "
                f"vs {b.raw_unit} ({b.unit}) — kein Vergleich möglich."
            ),
        }
    diff = abs(a.value - b.value)
    avg = (abs(a.value) + abs(b.value)) / 2 or 1.0
    rel = diff / avg
    matches = rel <= rel_tolerance
    return {
        "match": matches,
        "kind": "equal" if matches else "different",
        "a": {"value": a.value, "unit": a.unit, "raw_unit": a.raw_unit},
        "b": {"value": b.value, "unit": b.unit, "raw_unit": b.raw_unit},
        "rel_diff": rel,
        "abs_diff": diff,
        "reasoning": (
            f"Werte gleich innerhalb {rel_tolerance:.2%} Toleranz (rel. Abweichung {rel:.2%})."
            if matches
            else (
                f"Werte unterschiedlich: {a.value:g} {a.unit} vs {b.value:g} "
                f"{b.unit} (rel. Abweichung {rel:.2%}, Toleranz {rel_tolerance:.2%})."
            )
        ),
    }


def sum_quantities(qs: list[Quantity]) -> dict[str, Any]:
    """Sum a list of quantities. Requires same base unit across all
    entries; otherwise returns ``ok=False`` with a unit-mismatch hint.
    """
    if not qs:
        return {"ok": False, "reasoning": "Leere Eingabe — nichts zu summieren."}
    base = qs[0].unit
    if not all(q.unit == base for q in qs):
        units = sorted({q.raw_unit for q in qs})
        return {
            "ok": False,
            "reasoning": (
                f"Unterschiedliche Einheits-Dimensionen ({units}) — Summe "
                "nicht möglich. Vorher umrechnen oder Eingabe filtern."
            ),
            "raw_units": units,
        }
    total = sum(q.value for q in qs)
    return {
        "ok": True,
        "total": total,
        "unit": base,
        "raw_units": sorted({q.raw_unit for q in qs}),
        "reasoning": (f"Summe von {len(qs)} Werten in Einheit {base}: {total:g} {base}."),
    }


def best_pairwise_compare(
    a_qs: list[Quantity],
    b_qs: list[Quantity],
    *,
    rel_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Compare every pair across two quantity lists, return a summary
    plus the closest match (or closest miss).

    For evaluate-flow the closest match is what the LLM needs to know:
    "did the candidate's numbers line up with the claim's numbers?"
    """
    if not a_qs or not b_qs:
        return {
            "ok": False,
            "reasoning": "Eine der Eingaben enthält keine erkannten Zahlen.",
            "results": [],
        }
    results: list[dict[str, Any]] = []
    for a in a_qs:
        for b in b_qs:
            results.append(compare(a, b, rel_tolerance=rel_tolerance))
    matches = [r for r in results if r["match"]]
    closest = min(
        results,
        key=lambda r: (
            r.get("rel_diff", float("inf")) if r.get("kind") != "unit-mismatch" else float("inf")
        ),
    )
    return {
        "ok": True,
        "any_match": bool(matches),
        "n_matches": len(matches),
        "n_pairs": len(results),
        "results": results,
        "closest": closest,
        "reasoning": (
            f"{len(matches)} von {len(results)} Paaren stimmen überein "
            f"(Toleranz {rel_tolerance:.2%})."
            if matches
            else f"Keines von {len(results)} Paaren stimmt überein."
        ),
    }

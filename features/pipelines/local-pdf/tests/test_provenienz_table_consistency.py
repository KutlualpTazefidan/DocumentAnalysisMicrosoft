"""Tests for the TableConsistencyChecker tool."""

from __future__ import annotations

from local_pdf.provenienz.table_consistency import (
    check_consistency,
    render_report,
    to_dict,
)
from local_pdf.provenienz.table_parser import parse_table

TABLE_WITH_CORRECT_TOTAL = """
<table>
  <caption>Konservative Werte fuer drei Komponenten</caption>
  <tr><th>Groesse</th><th>A</th><th>B</th><th>C</th></tr>
  <tr><td>Wert</td><td>5</td><td>3</td><td>2</td></tr>
  <tr><td>Anteil</td><td>1</td><td>1</td><td>1</td></tr>
  <tr><td>Summe</td><td>6</td><td>4</td><td>3</td></tr>
</table>
"""

TABLE_WITH_WRONG_TOTAL = """
<table>
  <tr><th>Groesse</th><th>A</th><th>B</th></tr>
  <tr><td>Wert 1</td><td>5</td><td>3</td></tr>
  <tr><td>Wert 2</td><td>4</td><td>2</td></tr>
  <tr><td>Summe</td><td>10</td><td>6</td></tr>
</table>
"""

TABLE_WITH_UNIT_DRIFT = """
<table>
  <tr><th>Groesse</th><th>Wert</th></tr>
  <tr><td>Druck</td><td>5,5 MPa</td></tr>
  <tr><td>Anderer Druck</td><td>2 bar</td></tr>
</table>
"""

TABLE_NO_TOTAL_ROW = """
<table>
  <tr><th>Groesse</th><th>A</th><th>B</th></tr>
  <tr><td>Wert</td><td>5</td><td>3</td></tr>
</table>
"""


def test_correct_total_row_yields_no_issues():
    t = parse_table(TABLE_WITH_CORRECT_TOTAL)
    assert t is not None
    r = check_consistency(t)
    assert r.has_total_row is True
    assert all(i.kind != "column_sum_mismatch" for i in r.issues)
    # Computed sums should be present.
    assert r.column_sums_computed["A"] == 6.0
    assert r.column_sums_computed["B"] == 4.0
    assert r.column_sums_computed["C"] == 3.0


def test_wrong_total_row_flags_column_sum_mismatch():
    t = parse_table(TABLE_WITH_WRONG_TOTAL)
    assert t is not None
    r = check_consistency(t)
    assert r.has_total_row is True
    sum_issues = [i for i in r.issues if i.kind == "column_sum_mismatch"]
    # A: 5+4=9 but stated 10 → mismatch.
    # B: 3+2=5 but stated 6 → mismatch.
    assert len(sum_issues) == 2
    descs = " ".join(i.description for i in sum_issues)
    assert "Summe" in descs


def test_unit_drift_within_column_flags_warning():
    t = parse_table(TABLE_WITH_UNIT_DRIFT)
    assert t is not None
    r = check_consistency(t)
    drift_issues = [i for i in r.issues if i.kind == "unit_drift"]
    assert len(drift_issues) == 1
    assert drift_issues[0].severity == "warning"
    assert "MPa" in drift_issues[0].description
    assert "bar" in drift_issues[0].description


def test_table_without_total_row_skips_sum_check():
    t = parse_table(TABLE_NO_TOTAL_ROW)
    assert t is not None
    r = check_consistency(t)
    assert r.has_total_row is False
    assert all(i.kind != "column_sum_mismatch" for i in r.issues)


def test_render_report_clean_table_with_total():
    t = parse_table(TABLE_WITH_CORRECT_TOTAL)
    assert t is not None
    r = check_consistency(t)
    text = render_report(r)
    # Table HAS a Total row -> tool verified the sum; downstream LLM
    # may treat this as confirmation.
    assert "verifiziert" in text
    assert "Total-Zeile" in text


def test_render_report_no_total_row_flags_unverified():
    """Without a Total row the consistency tool can't run the column-
    sum check. The report must NOT read like 'no issues found' but
    explicitly flag the sum as UNVERIFIED so downstream prompts don't
    treat the silence as confirmation."""
    t = parse_table(TABLE_NO_TOTAL_ROW)
    assert t is not None
    r = check_consistency(t)
    text = render_report(r)
    assert "[UNVERIFIED]" in text
    assert "NICHT" in text  # the prompt explicitly says NICHT verifiziert


def test_render_report_with_issues():
    t = parse_table(TABLE_WITH_WRONG_TOTAL)
    assert t is not None
    r = check_consistency(t)
    text = render_report(r)
    assert "ERROR" in text
    assert "Summe" in text


def test_to_dict_serializes_full_report():
    t = parse_table(TABLE_WITH_WRONG_TOTAL)
    assert t is not None
    r = check_consistency(t)
    d = to_dict(r)
    assert d["has_total_row"] is True
    assert isinstance(d["issues"], list)
    assert len(d["issues"]) >= 2
    assert "reasoning" in d
    assert "ERROR" in d["reasoning"]


def test_tolerance_param_softens_strict_mismatch():
    """A 1% off total can be accepted by loosening the tolerance."""
    html = """
    <table>
      <tr><th>X</th><th>A</th></tr>
      <tr><td>v1</td><td>50</td></tr>
      <tr><td>v2</td><td>50</td></tr>
      <tr><td>Summe</td><td>101</td></tr>
    </table>
    """
    t = parse_table(html)
    assert t is not None
    # Strict: 100 vs 101 = 1% off, flagged.
    strict = check_consistency(t)
    assert any(i.kind == "column_sum_mismatch" for i in strict.issues)
    # Loose: 1.5% tolerance, not flagged.
    loose = check_consistency(t, sum_rel_tolerance=0.015)
    assert not any(i.kind == "column_sum_mismatch" for i in loose.issues)

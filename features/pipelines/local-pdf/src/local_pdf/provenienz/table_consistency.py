"""Internal-consistency checks for parsed tables.

Used by the TableConsistencyChecker tool. Operates on a
:class:`StructuredTable` (output of ``table_parser.parse_table``)
and reports issues that are detectable WITHOUT domain knowledge:

  - Column-sum mismatch: a 'Summe' / 'Total' / 'Gesamt' row exists
    but its value doesn't match the sum of the column's data rows.
  - Unit drift: cells in the same column carry different units —
    likely typo or unit-conversion gap.

Pure functions. Domain interpretation (whether a 'mismatch' is
acceptable as conservative bound, whether unit-drift is intentional
in a comparison-style table) stays in Skills.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from local_pdf.provenienz.calculator import parse_quantities

if TYPE_CHECKING:
    from local_pdf.provenienz.table_parser import StructuredTable


@dataclass(frozen=True)
class ConsistencyIssue:
    """One issue detected in a table.

    ``severity``:
      - ``"info"``: noteworthy but not necessarily wrong
      - ``"warning"``: probably wrong, worth flagging
      - ``"error"``: numeric inconsistency, almost certainly wrong
    """

    kind: str
    severity: str
    description: str


@dataclass(frozen=True)
class ConsistencyReport:
    n_rows_checked: int
    n_columns_checked: int
    issues: list[ConsistencyIssue]
    column_sums_computed: dict[str, float]
    units_per_column: dict[str, list[str]]
    has_total_row: bool


_TOTAL_LABELS = ("summe", "total", "gesamt", "sum")


def _is_total_row_label(label: str) -> bool:
    low = label.strip().lower()
    return any(t in low for t in _TOTAL_LABELS)


def _first_number_in_cell(cell_text: str) -> float | None:
    """Try to parse the first (number, unit) quantity from a cell. Returns
    the canonical-base value (kW → W, etc.) or None."""
    qs = parse_quantities(cell_text)
    if qs:
        return qs[0].value
    # Fallback: bare number with German decimal comma, no unit.
    s = cell_text.strip()
    if not s:
        return None
    s = s.replace(" ", "")
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


def check_consistency(
    table: StructuredTable, *, sum_rel_tolerance: float = 0.001
) -> ConsistencyReport:
    """Run internal-consistency checks on *table* and return a report.

    - ``sum_rel_tolerance``: how much computed-sum-vs-stated-total may
      differ before flagging. 0.1% is tight; rounding errors usually
      stay below that for engineering tables.
    """
    issues: list[ConsistencyIssue] = []

    total_row = next((r for r in table.rows if _is_total_row_label(r.label)), None)
    has_total = total_row is not None

    # Data columns are everything after the row-label column.
    data_columns = list(table.headers[1:])

    # --- 1) Column-sum mismatch ---
    column_sums: dict[str, float] = {}
    if total_row is not None:
        data_rows = [r for r in table.rows if r is not total_row]
        for col in data_columns:
            values: list[float] = []
            for r in data_rows:
                v = _first_number_in_cell(r.cells.get(col, ""))
                if v is not None:
                    values.append(v)
            if not values:
                continue
            computed = sum(values)
            column_sums[col] = computed
            stated = _first_number_in_cell(total_row.cells.get(col, ""))
            if stated is None:
                continue
            denom = max(abs(computed), abs(stated), 1e-9)
            rel_diff = abs(computed - stated) / denom
            if rel_diff > sum_rel_tolerance:
                issues.append(
                    ConsistencyIssue(
                        kind="column_sum_mismatch",
                        severity="error",
                        description=(
                            f"Spalte '{col}': Summe der Datenzeilen "
                            f"{computed:g} stimmt nicht mit Total-Zeile "
                            f"'{total_row.label}' = {stated:g} ueberein "
                            f"(rel. Diff {rel_diff:.4%}, Toleranz "
                            f"{sum_rel_tolerance:.4%})."
                        ),
                    )
                )

    # --- 2) Unit drift per column ---
    units_per_column: dict[str, list[str]] = {}
    for col in data_columns:
        seen: list[str] = []
        for r in table.rows:
            cell = r.cells.get(col, "")
            for q in parse_quantities(cell):
                if q.raw_unit not in seen:
                    seen.append(q.raw_unit)
        if seen:
            units_per_column[col] = seen
        if len(seen) > 1:
            # Multiple distinct units in the same column. Could be
            # legitimate (Auslegungs- vs Berechnungs-Einheit), but worth
            # flagging.
            issues.append(
                ConsistencyIssue(
                    kind="unit_drift",
                    severity="warning",
                    description=(
                        f"Spalte '{col}' enthaelt mehrere Einheiten: "
                        f"{', '.join(seen)}. Pruefe ob die Misch-Einheit "
                        "beabsichtigt ist (z.B. Vergleichs-Tabelle)."
                    ),
                )
            )

    return ConsistencyReport(
        n_rows_checked=len(table.rows),
        n_columns_checked=len(data_columns),
        issues=issues,
        column_sums_computed=column_sums,
        units_per_column=units_per_column,
        has_total_row=has_total,
    )


def render_report(report: ConsistencyReport) -> str:
    """Format the consistency report as a German prompt-block.

    The wording differentiates clearly between three states so the
    downstream LLM never reads 'no issues' as 'sum verified' when the
    tool actually couldn't run the sum check:

      - has_total_row + no issues   -> sum was verified by the tool
      - no has_total_row            -> sum was NOT verified; flagged as
                                        unverified with an explicit
                                        [UNVERIFIED] marker
      - any issues                  -> rendered with severity markers
    """
    lines: list[str] = []
    severity_count = {
        "error": sum(1 for i in report.issues if i.severity == "error"),
        "warning": sum(1 for i in report.issues if i.severity == "warning"),
        "info": sum(1 for i in report.issues if i.severity == "info"),
    }
    if not report.issues:
        if report.has_total_row:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. Spalten-Summe(n) "
                "stimmen mit der Total-Zeile ueberein (deterministisch "
                "vom Werkzeug verifiziert)."
            )
        else:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. [UNVERIFIED] "
                "Keine Total-Zeile in der Tabelle vorhanden — das "
                "Werkzeug konnte die Spalten-Summe NICHT gegen einen "
                "behaupteten Gesamtwert pruefen. Eine in der Aussage "
                "behauptete Summe ist damit NICHT verifiziert; sie "
                "muss anders gepruefte werden (z.B. Calculator auf "
                "Komponenten-Spalte)."
            )
        return "\n".join(lines)
    lines.append(
        f"Konsistenz-Pruefung: {len(report.issues)} Befund(e) "
        f"(Errors: {severity_count['error']}, Warnings: "
        f"{severity_count['warning']})."
    )
    for issue in report.issues:
        marker = {
            "error": "[ERROR]",
            "warning": "[WARNING]",
            "info": "[INFO]",
        }.get(issue.severity, "[?]")
        lines.append(f"- {marker} {issue.description}")
    return "\n".join(lines)


def to_dict(report: ConsistencyReport) -> dict[str, Any]:
    """Plain-dict representation for JSON persistence."""
    return {
        "n_rows_checked": report.n_rows_checked,
        "n_columns_checked": report.n_columns_checked,
        "has_total_row": report.has_total_row,
        "issues": [
            {"kind": i.kind, "severity": i.severity, "description": i.description}
            for i in report.issues
        ],
        "column_sums_computed": dict(report.column_sums_computed),
        "units_per_column": {k: list(v) for k, v in report.units_per_column.items()},
        "reasoning": render_report(report),
    }

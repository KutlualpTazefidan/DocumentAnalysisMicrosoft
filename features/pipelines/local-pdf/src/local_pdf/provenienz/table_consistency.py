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

from dataclasses import dataclass, field
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
    # When True a column whose header contains 'Summe'/'Total'/'Gesamt'
    # was found and each data row's stated total was compared against
    # the sum of its other numeric cells.
    has_total_column: bool = False
    # Per-row row-sum check: row.label -> (stated_total, computed_total)
    # for diagnostic rendering / downstream Calculator wiring.
    row_sums_computed: dict[str, tuple[float, float]] = field(default_factory=dict)


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


def _find_total_column(headers: list[str]) -> str | None:
    """Return the header text of the first column whose label looks
    like a total/sum aggregate (Summe / Total / Gesamt / Sum), or
    ``None``. The match is case-insensitive substring against the full
    header text so 'Summe im Behaelter, kW' matches just like 'Summe'.
    """
    for h in headers[1:]:
        if _is_total_row_label(h):
            return h
    return None


def check_consistency(
    table: StructuredTable, *, sum_rel_tolerance: float = 0.001
) -> ConsistencyReport:
    """Run internal-consistency checks on *table* and return a report.

    - ``sum_rel_tolerance``: how much computed-sum-vs-stated-total may
      differ before flagging. 0.1% is tight; rounding errors usually
      stay below that for engineering tables.

    Two axes:
      1. Column-sum vs Total-Zeile  (legacy)
      2. Row-sum vs Total-Spalte    (NEW — catches the 'Summe im
         Behaelter, kW' shape where the aggregate lives in a column,
         not a row)

    Plus a unit-drift check per column.
    """
    issues: list[ConsistencyIssue] = []

    total_row = next((r for r in table.rows if _is_total_row_label(r.label)), None)
    has_total = total_row is not None

    # Data columns are everything after the row-label column.
    data_columns = list(table.headers[1:])

    # Row-sum axis: detect a column whose header looks like a total.
    # All cells under that column are 'stated totals' for the row; we
    # compare each against the sum of preceding numeric cells in the
    # same row.
    total_column = _find_total_column(table.headers)
    has_total_column = total_column is not None
    row_sums: dict[str, tuple[float, float]] = {}
    if total_column is not None:
        # Component columns: everything strictly between the row-label
        # column and the total column. (Anything to the right of the
        # total column is not part of the aggregate.)
        try:
            total_col_idx = table.headers.index(total_column)
        except ValueError:
            total_col_idx = len(table.headers)
        component_columns = [h for h in table.headers[1:total_col_idx]]
        for r in table.rows:
            # Skip rows that themselves are a "Summe"-row — they belong
            # to the column-sum axis below, not the row-sum axis.
            if _is_total_row_label(r.label):
                continue
            component_values: list[float] = []
            for col in component_columns:
                v = _first_number_in_cell(r.cells.get(col, ""))
                if v is not None:
                    component_values.append(v)
            stated = _first_number_in_cell(r.cells.get(total_column, ""))
            if stated is None or not component_values:
                continue
            computed = sum(component_values)
            row_sums[r.label] = (stated, computed)
            denom = max(abs(computed), abs(stated), 1e-9)
            rel_diff = abs(computed - stated) / denom
            if rel_diff > sum_rel_tolerance:
                issues.append(
                    ConsistencyIssue(
                        kind="row_sum_mismatch",
                        severity="error",
                        description=(
                            f"Zeile '{r.label}': Summe der Komponenten-"
                            f"Spalten ({', '.join(component_columns)}) "
                            f"ergibt {computed:g}, die Total-Spalte "
                            f"'{total_column}' nennt aber {stated:g} "
                            f"(rel. Diff {rel_diff:.4%}, Toleranz "
                            f"{sum_rel_tolerance:.4%}). Die behauptete "
                            "Summe ist durch die einzelnen Komponenten-"
                            "Werte NICHT gedeckt — die Tabelle bildet "
                            "entweder ein abgeleitetes Aggregat ab "
                            "(Skalierungs-Faktor, gewichtete Summe), "
                            "oder es liegt ein Tabellen-Fehler vor."
                        ),
                    )
                )

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
        has_total_column=has_total_column,
        row_sums_computed=row_sums,
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
        if report.has_total_row and report.has_total_column:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. Spalten-Summe(n) "
                "stimmen mit der Total-Zeile UND Zeilen-Summe(n) stimmen "
                "mit der Total-Spalte ueberein (deterministisch vom "
                "Werkzeug verifiziert)."
            )
        elif report.has_total_row:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. Spalten-Summe(n) "
                "stimmen mit der Total-Zeile ueberein (deterministisch "
                "vom Werkzeug verifiziert)."
            )
        elif report.has_total_column:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. Zeilen-Summe(n) "
                "stimmen mit der Total-Spalte ueberein (deterministisch "
                "vom Werkzeug verifiziert)."
            )
        else:
            lines.append(
                f"Konsistenz-Pruefung: {report.n_rows_checked} Zeilen x "
                f"{report.n_columns_checked} Spalten. [UNVERIFIED] "
                "Weder Total-Zeile noch Total-Spalte in der Tabelle "
                "vorhanden — das Werkzeug konnte keinen Summen-"
                "Quervergleich gegen einen behaupteten Gesamtwert "
                "fuehren. Eine in der Aussage behauptete Summe ist "
                "damit NICHT verifiziert."
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
        "has_total_column": report.has_total_column,
        "issues": [
            {"kind": i.kind, "severity": i.severity, "description": i.description}
            for i in report.issues
        ],
        "column_sums_computed": dict(report.column_sums_computed),
        "row_sums_computed": {
            k: {"stated": v[0], "computed": v[1]} for k, v in report.row_sums_computed.items()
        },
        "units_per_column": {k: list(v) for k, v in report.units_per_column.items()},
        "reasoning": render_report(report),
    }

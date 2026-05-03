import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { BoxKind, SegmentBox } from "../types/domain";
import { T } from "../styles/typography";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "auxiliary", "discard"];

// ── Page-state helpers ─────────────────────────────────────────────────────────

type PageState = "no-segmentation" | "segmented" | "approved";

function pageStateFor(
  pageNum: number,
  segmentedPages: Set<number>,
  approvedPages: Set<number>,
): PageState {
  if (approvedPages.has(pageNum)) return "approved";
  if (segmentedPages.has(pageNum)) return "segmented";
  return "no-segmentation";
}

function pageButtonClasses(state: PageState, isActive: boolean): string {
  const base = `w-10 h-10 rounded ${T.body} font-medium flex items-center justify-center transition-colors`;
  const ring = isActive ? " ring-2 ring-blue-500" : "";
  switch (state) {
    case "approved":
      return `${base} bg-blue-100 hover:bg-blue-200 text-blue-800${ring}`;
    case "segmented":
      return `${base} bg-green-100 hover:bg-green-200 text-green-800${ring}`;
    case "no-segmentation":
    default:
      return `${base} bg-red-100 hover:bg-red-200 text-red-800${ring}`;
  }
}

// ── Approval helpers (v1: localStorage) ───────────────────────────────────────

function approvedPagesKey(slug: string): string {
  return `segment.approved.${slug}`;
}

export function loadApprovedSegmentPages(slug: string): Set<number> {
  try {
    const raw = localStorage.getItem(approvedPagesKey(slug));
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as number[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

export function saveApprovedSegmentPages(slug: string, pages: Set<number>): void {
  localStorage.setItem(approvedPagesKey(slug), JSON.stringify([...pages]));
}

interface Props {
  slug: string;
  selected: SegmentBox | null;
  pageBoxCount: number;
  currentPage: number;
  totalPages: number;
  /** Set of page numbers that have at least one segmentation box */
  segmentedPages: Set<number>;
  /** Set of page numbers approved by user (controlled externally) */
  approvedPages: Set<number>;
  onToggleApprove: () => void;
  onResegmentPage: () => void;
  onResetPage: () => void;
  running: boolean;
  onChangeKind: (k: BoxKind) => void;
  onNewBox: () => void;
  onDeleteBox: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
  onResetBox: () => void;
  onMergeUp: () => void;
  onMergeDown: () => void;
  onUnmergeUp: () => void;
  onUnmergeDown: () => void;
  onPageChange: (page: number) => void;
  /** Effective threshold for the current page (default or per-page override) */
  perPageThreshold: number;
  /** Whether a per-page override exists for the current page */
  hasOverride: boolean;
  /** Write a per-page override for the current page */
  onPerPageChange: (v: number) => void;
  /** Clear the per-page override for the current page */
  onClearPerPage: () => void;
}

export function PropertiesSidebar({
  slug: _slug,
  selected,
  pageBoxCount,
  currentPage,
  totalPages,
  segmentedPages,
  approvedPages,
  onToggleApprove,
  onResegmentPage,
  onResetPage,
  running,
  onChangeKind,
  onNewBox,
  onDeleteBox,
  onDeactivate,
  onActivate,
  onResetBox,
  onMergeUp,
  onMergeDown,
  onUnmergeUp,
  onUnmergeDown,
  onPageChange,
  perPageThreshold,
  hasOverride,
  onPerPageChange,
  onClearPerPage,
}: Props): JSX.Element {
  const [gridOpen, setGridOpen] = useState(false);
  const currentState = pageStateFor(currentPage, segmentedPages, approvedPages);
  return (
    <aside className="w-80 border-l px-4 py-4 flex flex-col gap-3 bg-white overflow-y-auto">
      {/* ── Legend strip — single line, always visible ──────────────── */}
      <div className={`flex items-center justify-between gap-1 ${T.tiny} text-slate-600 whitespace-nowrap`}>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-red-200 shrink-0" aria-hidden="true" />
          Nicht segm.
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-green-200 shrink-0" aria-hidden="true" />
          Segmentiert
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-blue-200 shrink-0" aria-hidden="true" />
          Gesperrt
        </span>
      </div>

      {/* ── Single page button — toggles the grid below ──────────────── */}
      <button
        aria-label={`Seite ${currentPage} von ${totalPages}, ${gridOpen ? "Liste schließen" : "Liste öffnen"}`}
        aria-expanded={gridOpen}
        onClick={() => setGridOpen((p) => !p)}
        className={`${pageButtonClasses(currentState, true)} w-full !h-9 flex items-center justify-center gap-1 ${T.body} transition-colors`}
        data-testid="seg-page-grid-toggle"
      >
        <span>Seite {currentPage} / {totalPages}</span>
        <motion.span
          aria-hidden="true"
          animate={{ rotate: gridOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          ▾
        </motion.span>
      </button>

      {/* ── Animated grid (expand/collapse) ──────────────────────────── */}
      <AnimatePresence initial={false}>
        {gridOpen && (
          <motion.div
            key="seg-page-grid"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            <div
              className="grid grid-cols-5 gap-1 pt-1 max-h-64 overflow-y-auto pr-1"
              role="group"
              aria-label="Page navigation"
            >
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => {
                const state = pageStateFor(p, segmentedPages, approvedPages);
                return (
                  <button
                    key={p}
                    aria-label={`Page ${p}`}
                    aria-pressed={p === currentPage}
                    className={`${pageButtonClasses(state, p === currentPage)} transition-colors`}
                    onClick={() => {
                      onPageChange(p);
                      setGridOpen(false);
                    }}
                    data-testid={`seg-page-btn-${p}`}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <hr className="border-slate-200" />

      {/* ── Re-segment current page ──────────────────────────────────── */}
      <button
        aria-label={segmentedPages.has(currentPage) ? "Diese Seite neu segmentieren" : "Nur diese Seite segmentieren"}
        title={
          approvedPages.has(currentPage)
            ? "Seite ist gesperrt. Erst entsperren um neu zu segmentieren."
            : undefined
        }
        className={`w-full ${T.body} px-3 py-1.5 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
        disabled={running || approvedPages.has(currentPage)}
        onClick={onResegmentPage}
      >
        {segmentedPages.has(currentPage)
          ? "Diese Seite neu segmentieren"
          : "Nur diese Seite segmentieren"}
      </button>

      {/* ── Lock / unlock current page ────────────────────────────────── */}
      <button
        aria-label={approvedPages.has(currentPage) ? "Seite entsperren" : "Seite sperren"}
        className={
          approvedPages.has(currentPage)
            ? `${T.body} px-3 py-1.5 rounded border border-blue-400 bg-blue-100 text-blue-800 hover:bg-blue-200 w-full`
            : `${T.body} px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 w-full`
        }
        onClick={onToggleApprove}
      >
        {approvedPages.has(currentPage) ? "🔓 Seite entsperren" : "🔒 Seite sperren"}
      </button>

      {/* ── Per-page confidence slider ─────────────────────────────────── */}
      <div className="flex flex-col gap-1">
        <span className={T.bodyMuted}>Confidence (Seite {currentPage})</span>
        <div className="flex items-center gap-2">
          <input
            data-testid="per-page-conf-slider"
            aria-label={`Confidence threshold for page ${currentPage}`}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={perPageThreshold}
            onChange={(e) => onPerPageChange(parseFloat(e.target.value))}
            className="flex-1 accent-blue-500"
          />
          <span className={`${T.mono} text-slate-700 w-8 text-center`}>{perPageThreshold.toFixed(2)}</span>
          <button
            data-testid="per-page-conf-reset"
            aria-label="Reset per-page confidence override"
            title="Zurück auf Standard"
            disabled={!hasOverride}
            className="text-slate-400 hover:text-slate-700 disabled:opacity-30 disabled:cursor-not-allowed px-1"
            onClick={onClearPerPage}
          >
            ↺
          </button>
        </div>
      </div>

      {/* ── Page action buttons ────────────────────────────────────────── */}
      <button
        className={`w-full px-3 py-1.5 rounded border border-slate-300 text-slate-700 ${T.bodyMedium} hover:bg-slate-50`}
        onClick={onNewBox}
      >
        New box
      </button>

      <button
        aria-label="Delete box"
        title={!selected ? "Wähle zuerst eine Box aus" : `Box ${selected.box_id} löschen`}
        className={`w-full px-3 py-1.5 rounded border border-red-300 text-red-700 ${T.bodyMedium} hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed`}
        disabled={!selected}
        onClick={onDeleteBox}
      >
        Delete box
      </button>

      <button
        aria-label="Reset diese Seite"
        className={`w-full px-3 py-1.5 rounded border border-slate-300 text-slate-700 ${T.bodyMedium} hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed`}
        disabled={running}
        onClick={onResetPage}
      >
        Reset diese Seite
      </button>

      <hr className="border-slate-200" />

      {/* ── Section: Properties ────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <span className={T.tinyBold}>Properties</span>

        {selected ? (
          <>
            <div>
              <label className={`block ${T.bodyMuted}`}>Kind</label>
              <select
                className="w-full border rounded p-1 text-slate-900"
                value={selected.kind}
                onChange={(e) => onChangeKind(e.target.value as BoxKind)}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>

            <div className={`${T.body} text-slate-700`}>
              Confidence: {selected.confidence.toFixed(2)}
            </div>

            {/* Bbox 2x2 grid */}
            <div>
              <span className={T.bodyMuted}>bbox</span>
              <div className={`grid grid-cols-2 gap-1 ${T.mono} mt-1`}>
                <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                  x0: {selected.bbox[0].toFixed(3)}
                </div>
                <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                  y0: {selected.bbox[1].toFixed(3)}
                </div>
                <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                  x1: {selected.bbox[2].toFixed(3)}
                </div>
                <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                  y1: {selected.bbox[3].toFixed(3)}
                </div>
              </div>
            </div>

            {/* Action row: Merge/Unmerge up (left) | Merge/Unmerge down (right) */}
            <div className="grid grid-cols-2 gap-2">
              {selected.continues_from ? (
                <button
                  aria-label="Unmerge up"
                  className="px-2 py-1 rounded border border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200"
                  onClick={onUnmergeUp}
                >
                  Unmerge ↑
                </button>
              ) : (
                <button
                  aria-label="Merge up"
                  disabled={currentPage <= 1}
                  className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  onClick={onMergeUp}
                >
                  Merge up
                </button>
              )}
              {selected.continues_to ? (
                <button
                  aria-label="Unmerge down"
                  className="px-2 py-1 rounded border border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200"
                  onClick={onUnmergeDown}
                >
                  Unmerge ↓
                </button>
              ) : (
                <button
                  aria-label="Merge down"
                  disabled={currentPage >= totalPages}
                  className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                  onClick={onMergeDown}
                >
                  Merge down
                </button>
              )}
            </div>

            {/* Action row: Deactivate (left) | Activate (right) */}
            <div className="grid grid-cols-2 gap-2">
              <button
                aria-label="Deactivate"
                className={`px-2 py-1 rounded ${
                  selected.kind === "discard"
                    ? "bg-red-700 text-white border border-red-700"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50"
                }`}
                onClick={onDeactivate}
              >
                {selected.kind === "discard" ? "✓ Deactivated" : "Deactivate"}
              </button>
              <button
                aria-label="Activate"
                className={`px-2 py-1 rounded ${
                  selected.manually_activated
                    ? "bg-green-700 text-white border border-green-700"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50"
                }`}
                onClick={onActivate}
              >
                {selected.manually_activated ? "✓ Activated" : "Activate"}
              </button>
            </div>

            {/* Reset — full-width below */}
            <button
              aria-label="Reset box"
              className="w-full px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50"
              onClick={onResetBox}
            >
              Reset
            </button>
          </>
        ) : (
          <p className="text-slate-400">Wähle eine Box aus</p>
        )}
      </div>

      <div className="border-t border-slate-200 pt-3 mt-auto">
        <p className={T.bodyMuted}>{pageBoxCount} boxes on page</p>
      </div>
    </aside>
  );
}

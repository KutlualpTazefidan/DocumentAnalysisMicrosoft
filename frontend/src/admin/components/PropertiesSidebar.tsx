import type { BoxKind, SegmentBox } from "../types/domain";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Pagination } from "./Pagination";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "abandon", "discard"];

interface Props {
  selected: SegmentBox | null;
  pageBoxCount: number;
  currentPage: number;
  totalPages: number;
  confidenceThreshold: number;
  showDeactivated: boolean;
  onConfidenceChange: (v: number) => void;
  onShowDeactivatedChange: (v: boolean) => void;
  onRunExtractThisPage: () => void;
  onResetPage: () => void;
  extractEnabled: boolean;
  running: boolean;
  onChangeKind: (k: BoxKind) => void;
  onNewBox: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
  onResetBox: () => void;
  onMergeUp: () => void;
  onMergeDown: () => void;
  onPageChange: (page: number) => void;
}

export function PropertiesSidebar({
  selected,
  pageBoxCount,
  currentPage,
  totalPages,
  confidenceThreshold,
  showDeactivated,
  onConfidenceChange,
  onShowDeactivatedChange,
  onRunExtractThisPage,
  onResetPage,
  extractEnabled,
  running,
  onChangeKind,
  onNewBox,
  onDeactivate,
  onActivate,
  onResetBox,
  onMergeUp,
  onMergeDown,
  onPageChange,
}: Props): JSX.Element {
  return (
    <aside className="w-80 border-l px-8 py-4 flex flex-col gap-3 text-sm bg-white overflow-y-auto">
      {/* ── Pagination ─────────────────────────────────────────────── */}
      <div className="flex justify-center">
        <Pagination page={currentPage} totalPages={totalPages} onPageChange={onPageChange} />
      </div>

      <div className="flex items-center justify-center gap-2">
        <button
          aria-label="Previous page"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="w-7 h-7 rounded hover:bg-slate-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="w-4 h-4 text-slate-700" />
        </button>

        <h2 className="font-semibold text-slate-900 text-center min-w-[6rem]">
          Seite {currentPage} / {totalPages}
        </h2>

        <button
          aria-label="Next page"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="w-7 h-7 rounded hover:bg-slate-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight className="w-4 h-4 text-slate-700" />
        </button>
      </div>

      <hr className="my-3 border-slate-200" />

      {/* ── Section: Filter ────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Filter</span>

        <div className="flex items-center gap-2">
          <label htmlFor="conf-slider" className="text-xs text-slate-700 whitespace-nowrap">
            Conf ≥ {confidenceThreshold.toFixed(2)}
          </label>
          <input
            id="conf-slider"
            aria-label="Confidence threshold"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidenceThreshold}
            onChange={(e) => onConfidenceChange(parseFloat(e.target.value))}
            className="flex-1 accent-blue-600"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
          <input
            aria-label="Show deactivated"
            type="checkbox"
            checked={showDeactivated}
            onChange={(e) => onShowDeactivatedChange(e.target.checked)}
            className="accent-blue-600"
          />
          Show deactivated
        </label>
      </div>

      {/* ── Page action buttons ────────────────────────────────────── */}
      <button
        className="w-full py-2 rounded border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-50"
        onClick={onNewBox}
      >
        New box
      </button>

      <button
        aria-label="Reset diese Seite"
        className="w-full py-2 rounded border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={running}
        onClick={onResetPage}
      >
        Reset diese Seite
      </button>

      <button
        aria-label="Nur diese Seite extrahieren"
        className="w-full py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
        disabled={!extractEnabled || running}
        onClick={onRunExtractThisPage}
      >
        {running ? "Running…" : "Nur diese Seite extrahieren"}
      </button>

      <hr className="my-3 border-slate-200" />

      {/* ── Section: Properties ────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Properties</span>

        {selected ? (
          <>
            <div>
              <label className="block text-xs text-slate-500">Kind</label>
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

            <div className="text-xs text-slate-700">
              Confidence: {selected.confidence.toFixed(2)}
            </div>

            {/* Bbox 2x2 grid */}
            <div>
              <span className="text-xs text-slate-500">bbox</span>
              <div className="grid grid-cols-2 gap-1 text-xs font-mono mt-1">
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

            {/* Action row: Merge up (left) | Merge down (right) */}
            <div className="grid grid-cols-2 gap-2">
              <button
                aria-label="Merge up"
                disabled={currentPage <= 1 || !!selected.continues_from}
                className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                onClick={onMergeUp}
              >
                Merge up
              </button>
              <button
                aria-label="Merge down"
                disabled={currentPage >= totalPages || !!selected.continues_to}
                className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                onClick={onMergeDown}
              >
                Merge down
              </button>
            </div>

            {/* Action row: Deactivate (left) | Activate (right) */}
            <div className="grid grid-cols-2 gap-2">
              <button
                aria-label="Deactivate"
                className={`px-2 py-1 rounded ${
                  selected.kind === "discard"
                    ? "bg-red-700 text-white border border-red-700"  // chosen → strong red filled
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50"  // not chosen → outline
                }`}
                onClick={onDeactivate}
              >
                {selected.kind === "discard" ? "✓ Deactivated" : "Deactivate"}
              </button>
              <button
                aria-label="Activate"
                className={`px-2 py-1 rounded ${
                  selected.manually_activated
                    ? "bg-green-700 text-white border border-green-700"  // chosen → strong green filled
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50"  // not chosen → outline
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
        <p className="text-xs text-slate-500">{pageBoxCount} boxes on page</p>
      </div>
    </aside>
  );
}

import type { BoxKind, SegmentBox } from "../types/domain";
import { Pagination } from "./Pagination";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"];

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
  onResetBox: () => void;
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
  onResetBox,
  onPageChange,
}: Props): JSX.Element {
  return (
    <aside className="w-72 border-l p-4 flex flex-col gap-3 text-sm bg-white overflow-y-auto">
      {/* ── Pagination ─────────────────────────────────────────────── */}
      <div className="flex justify-center">
        <Pagination page={currentPage} totalPages={totalPages} onPageChange={onPageChange} />
      </div>

      <div className="text-center text-slate-700 font-medium">
        <h2 className="font-semibold text-slate-900">
          Seite {currentPage} / {totalPages}
        </h2>
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
        aria-label="Nur diese Seite extrahieren"
        className="w-full py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
        disabled={!extractEnabled || running}
        onClick={onRunExtractThisPage}
      >
        {running ? "Running…" : "Nur diese Seite extrahieren"}
      </button>

      <button
        aria-label="Reset diese Seite"
        className="w-full py-2 rounded border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
        disabled={running}
        onClick={onResetPage}
      >
        Reset diese Seite
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

            {/* Action row: New box (left) | Deactivate (right) */}
            <div className="grid grid-cols-2 gap-2">
              <button
                className="px-2 py-1 border rounded text-slate-700 hover:bg-slate-50"
                onClick={onNewBox}
              >
                New box
              </button>
              <button
                aria-label="Deactivate"
                className="px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white"
                onClick={onDeactivate}
              >
                Deactivate
              </button>
            </div>

            {/* Reset selected box — full-width secondary */}
            <button
              aria-label="Reset box"
              className="w-full py-1 rounded border border-slate-300 text-slate-700 text-sm hover:bg-slate-50"
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

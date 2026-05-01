import type { BoxKind, SegmentBox } from "../types/domain";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"];

interface Props {
  selected: SegmentBox | null;
  pageBoxCount: number;
  onChangeKind: (k: BoxKind) => void;
  onMerge: () => void;
  onDeactivate: () => void;
  // Filter controls (moved from top bar)
  confidenceThreshold: number;
  onConfidenceChange: (v: number) => void;
  showDeactivated: boolean;
  onShowDeactivatedChange: (v: boolean) => void;
  // Per-page extract
  onExtractThisPage: () => void;
  extractRunning: boolean;
  extractEnabled: boolean;
}

export function PropertiesSidebar({
  selected,
  pageBoxCount,
  onChangeKind,
  onMerge,
  onDeactivate,
  confidenceThreshold,
  onConfidenceChange,
  showDeactivated,
  onShowDeactivatedChange,
  onExtractThisPage,
  extractRunning,
  extractEnabled,
}: Props): JSX.Element {
  return (
    <aside className="w-72 border-l p-4 flex flex-col gap-3 text-sm bg-white">
      <h2 className="font-semibold text-slate-900">Properties</h2>

      {/* ── Filter section ─────────────────────────────────────────── */}
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wide">Filter</h3>

        {/* Confidence slider */}
        <div className="flex flex-col gap-1">
          <label htmlFor="conf-slider" className="text-xs text-slate-700">
            Confidence ≥ {confidenceThreshold.toFixed(2)}
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
            className="w-full accent-blue-600"
          />
        </div>

        {/* Show deactivated checkbox */}
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
      </section>

      <div className="border-t border-slate-200" />

      {/* ── Selected Box section ────────────────────────────────────── */}
      <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wide">Selected Box</h3>

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

          {/* Bbox 2x2 grid */}
          <div>
            <span className="text-xs text-slate-500">bbox</span>
            <div className="grid grid-cols-2 gap-1 text-xs font-mono mt-1">
              <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                x0: {selected.bbox[0]}
              </div>
              <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                y0: {selected.bbox[1]}
              </div>
              <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                x1: {selected.bbox[2]}
              </div>
              <div className="border border-slate-200 rounded px-2 py-1 text-slate-800">
                y1: {selected.bbox[3]}
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              {selected.bbox[2] - selected.bbox[0]} × {selected.bbox[3] - selected.bbox[1]}
            </p>
          </div>

          <div>
            <span className="text-xs text-slate-500">confidence</span>{" "}
            <span className="text-slate-900">{selected.confidence.toFixed(3)}</span>
          </div>

          <div className="flex gap-2">
            <button className="px-2 py-1 border rounded text-slate-700 hover:bg-slate-50" onClick={onMerge}>
              Merge (m)
            </button>
            <button
              className="px-2 py-1 border rounded text-slate-700 hover:bg-slate-50"
              onClick={onDeactivate}
            >
              Deactivate
            </button>
          </div>
        </>
      ) : (
        <p className="text-slate-400">Select a box.</p>
      )}

      <div className="border-t border-slate-200 pt-3 mt-3">
        <p className="text-xs text-slate-500">{pageBoxCount} boxes on page</p>
      </div>

      {/* Per-page extract */}
      <button
        aria-label="Nur diese Seite extrahieren"
        className="mt-1 text-xs bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded disabled:bg-gray-300 disabled:cursor-not-allowed"
        disabled={!extractEnabled || extractRunning}
        onClick={onExtractThisPage}
      >
        {extractRunning ? "Running…" : "Nur diese Seite extrahieren"}
      </button>
    </aside>
  );
}

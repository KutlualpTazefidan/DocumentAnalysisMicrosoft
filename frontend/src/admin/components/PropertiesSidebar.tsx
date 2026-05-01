import type { BoxKind, SegmentBox } from "../types/domain";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"];

interface Props {
  selected: SegmentBox | null;
  pageBoxCount: number;
  onChangeKind: (k: BoxKind) => void;
  onSplit: () => void;
  onNewBox: () => void;
}

export function PropertiesSidebar({
  selected,
  pageBoxCount,
  onChangeKind,
  onSplit,
  onNewBox,
}: Props): JSX.Element {
  return (
    <aside className="w-72 border-l p-4 flex flex-col gap-3 text-sm bg-white">
      <h2 className="font-semibold text-slate-900">Properties</h2>

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

          <div>
            <span className="text-xs text-slate-500">confidence</span>{" "}
            <span className="text-slate-900">{selected.confidence.toFixed(3)}</span>
          </div>

          <div className="flex gap-2">
            <button className="px-2 py-1 border rounded text-slate-700 hover:bg-slate-50" onClick={onSplit}>
              Split (/)
            </button>
            <button className="px-2 py-1 border rounded text-slate-700 hover:bg-slate-50" onClick={onNewBox}>
              New box (n)
            </button>
          </div>
        </>
      ) : (
        <p className="text-slate-400">Select a box.</p>
      )}

      <div className="border-t border-slate-200 pt-3 mt-3">
        <p className="text-xs text-slate-500">{pageBoxCount} boxes on page</p>
      </div>
    </aside>
  );
}

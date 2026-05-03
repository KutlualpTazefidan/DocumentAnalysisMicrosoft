import type { BoxKind, SegmentBox } from "../types/domain";
import { T } from "../styles/typography";

const KINDS: BoxKind[] = [
  "heading",
  "paragraph",
  "table",
  "figure",
  "caption",
  "formula",
  "list_item",
  "auxiliary",
  "discard",
];

interface Props {
  selected: SegmentBox | null;
  currentPage: number;
  totalPages: number;
  onChangeKind: (k: BoxKind) => void;
  onDeactivate: () => void;
  onActivate: () => void;
  onResetBox: () => void;
  onMergeUp: () => void;
  onMergeDown: () => void;
  onUnmergeUp: () => void;
  onUnmergeDown: () => void;
  /** True while a box-mutation request is in flight — disables Activate /
   *  Deactivate and surfaces a loading indicator on the active button. */
  pending?: boolean;
  /** Raw html_snippet from mineru.json for the selected box. Shown in a
   *  collapsible "Quelltext" panel so the user can verify what MinerU
   *  actually produced (vs. what the renderer/transformations show). */
  rawSnippet?: string;
}

/**
 * Box-properties panel shared between segment and extract sidebars.
 *
 * When a box is selected, shows: kind dropdown, confidence, bbox coords,
 * merge/unmerge up/down, deactivate/activate, reset.  Empty placeholder
 * when nothing is selected.
 *
 * The actual mutation hooks (useUpdateBox, useMergeBoxDown, etc.) are wired
 * by the parent route — this is a presentational component.
 */
export function BoxPropertiesPanel({
  selected,
  currentPage,
  totalPages,
  onChangeKind,
  onDeactivate,
  onActivate,
  onResetBox,
  onMergeUp,
  onMergeDown,
  onUnmergeUp,
  onUnmergeDown,
  pending = false,
  rawSnippet,
}: Props): JSX.Element {
  const isActive = selected ? selected.kind !== "discard" : false;
  return (
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

          {/* Merge/Unmerge up | down */}
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

          {/* Deactivate | Activate — Activated highlight = currently active
              (kind != discard); pending state on either button shows the
              html refresh is in flight. */}
          <div className="grid grid-cols-2 gap-2">
            <button
              aria-label="Deactivate"
              disabled={pending}
              className={`px-2 py-1 rounded disabled:opacity-50 disabled:cursor-not-allowed ${
                selected.kind === "discard"
                  ? "bg-red-700 text-white border border-red-700"
                  : "border border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              onClick={onDeactivate}
            >
              {pending && !isActive
                ? "…"
                : selected.kind === "discard"
                  ? "✓ Deactivated"
                  : "Deactivate"}
            </button>
            <button
              aria-label="Activate"
              disabled={pending}
              className={`px-2 py-1 rounded disabled:opacity-50 disabled:cursor-not-allowed ${
                isActive
                  ? "bg-green-700 text-white border border-green-700"
                  : "border border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              onClick={onActivate}
            >
              {pending && isActive ? "…" : isActive ? "✓ Activated" : "Activate"}
            </button>
          </div>

          <button
            aria-label="Reset box"
            className="w-full px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50"
            onClick={onResetBox}
          >
            Reset
          </button>

          {rawSnippet !== undefined && (
            <details className="mt-2 group">
              <summary className={`${T.tinyBold} cursor-pointer text-slate-700 select-none`}>
                Quelltext (mineru.json)
              </summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded border border-slate-200 bg-slate-50 p-2 text-[11px] leading-snug font-mono text-slate-700">
                {rawSnippet || "(leer)"}
              </pre>
              <button
                type="button"
                className="mt-1 text-xs text-blue-600 hover:underline disabled:text-slate-400"
                disabled={!rawSnippet}
                onClick={() => {
                  if (rawSnippet) navigator.clipboard?.writeText(rawSnippet);
                }}
              >
                kopieren
              </button>
            </details>
          )}
        </>
      ) : (
        <p className="text-slate-400">Wähle eine Box aus</p>
      )}
    </div>
  );
}

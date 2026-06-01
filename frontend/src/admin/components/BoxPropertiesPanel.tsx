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
  "toc",
  "list_of_tables",
  "list_of_figures",
  "bibliography",
  "discard",
];

// Human-readable labels for the dropdown. Without this the user sees the
// raw enum values; with it Verzeichnis kinds show their proper German
// names so manual reclassification matches the badges and detection
// hints.
const KIND_LABELS: Record<BoxKind, string> = {
  heading: "heading",
  paragraph: "paragraph",
  table: "table",
  figure: "figure",
  caption: "caption",
  formula: "formula",
  list_item: "list_item",
  auxiliary: "auxiliary",
  toc: "Inhaltsverzeichnis",
  list_of_tables: "Tabellenverzeichnis",
  list_of_figures: "Abbildungsverzeichnis",
  bibliography: "Literaturverzeichnis",
  discard: "discard",
};

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
      <span className={T.tinyBold}>Eigenschaften</span>

      {selected ? (
        <>
          {/* ── Tier 1: primary — the per-box decisions made constantly ── */}
          <div>
            <label className={`block ${T.bodyMuted}`}>Typ</label>
            <select
              className="w-full border rounded p-1 text-slate-900"
              value={selected.kind}
              onChange={(e) => onChangeKind(e.target.value as BoxKind)}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </div>

          <div className={`${T.body} text-slate-700`}>
            Konfidenz: {selected.confidence.toFixed(2)}
          </div>

          {/* Deactivate | Activate — Activated highlight = currently active
              (kind != discard); pending state shows the html refresh in flight. */}
          <div className="grid grid-cols-2 gap-2">
            <button
              aria-label="Deactivate"
              disabled={pending}
              className={`${T.body} px-2 py-1 rounded disabled:opacity-50 disabled:cursor-not-allowed ${
                selected.kind === "discard"
                  ? "bg-red-700 text-white border border-red-700"
                  : "border border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              onClick={onDeactivate}
            >
              {pending && !isActive
                ? "…"
                : selected.kind === "discard"
                  ? "✓ Deaktiviert"
                  : "Deaktivieren"}
            </button>
            <button
              aria-label="Activate"
              disabled={pending}
              className={`${T.body} px-2 py-1 rounded disabled:opacity-50 disabled:cursor-not-allowed ${
                isActive
                  ? "bg-green-700 text-white border border-green-700"
                  : "border border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
              onClick={onActivate}
            >
              {pending && isActive ? "…" : isActive ? "✓ Aktiv" : "Aktivieren"}
            </button>
          </div>

          {/* ── Tier 2: structure — merge/unmerge with adjacent pages ── */}
          <div>
            <span className={T.bodyMuted}>Struktur</span>
            <div className="grid grid-cols-2 gap-2 mt-1">
              {selected.continues_from ? (
                <button
                  aria-label="Unmerge up"
                  className={`${T.body} px-2 py-1 rounded border border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200`}
                  onClick={onUnmergeUp}
                >
                  Trennen ↑
                </button>
              ) : (
                <button
                  aria-label="Merge up"
                  disabled={currentPage <= 1}
                  className={`${T.body} px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
                  onClick={onMergeUp}
                >
                  Verbinden ↑
                </button>
              )}
              {selected.continues_to ? (
                <button
                  aria-label="Unmerge down"
                  className={`${T.body} px-2 py-1 rounded border border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200`}
                  onClick={onUnmergeDown}
                >
                  Trennen ↓
                </button>
              ) : (
                <button
                  aria-label="Merge down"
                  disabled={currentPage >= totalPages}
                  className={`${T.body} px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
                  onClick={onMergeDown}
                >
                  Verbinden ↓
                </button>
              )}
            </div>
          </div>

          {/* ── Tier 3: rare — folded away by default ── */}
          <details className="group">
            <summary className={`${T.tinyBold} cursor-pointer text-slate-700 select-none`}>
              Mehr
            </summary>
            <div className="flex flex-col gap-3 mt-2">
              <button
                aria-label="Reset box"
                className={`${T.body} w-full px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50`}
                onClick={onResetBox}
              >
                Zurücksetzen
              </button>

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

              {rawSnippet !== undefined && (
                <details className="group">
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
            </div>
          </details>
        </>
      ) : (
        <p className="text-slate-400">Wähle eine Box aus</p>
      )}
    </div>
  );
}

import { BookOpen } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { SearchResultsBagView } from "../layout";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-100 text-emerald-800",
  "partial-support": "bg-amber-100 text-amber-800",
  unrelated: "bg-canvas text-ink-muted",
  contradicts: "bg-rose-100 text-rose-800",
  manual: "bg-purple-100 text-purple-800",
};

const ROW_HEIGHT_PX = 44; // approximate; aligns the per-row handles

/**
 * One tile per task that has search_results, listing all results as rows.
 * Each row exposes its own bottom-edge source handle (id="row-{nodeId}") so
 * a "promote-to-chunk" action can attach a new exploration tile to *that
 * specific row* rather than the bag as a whole.
 */
export function SearchResultsBagTile({
  data,
}: NodeProps<SearchResultsBagView>): JSX.Element {
  const evaluatedCount = data.rows.filter((r) => r.evaluation).length;
  const rows = data.rows.slice(0, 10);

  return (
    <div className="prov-tile border-emerald-500 w-80 relative">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-2 px-3 py-2 border-b border-emerald-200">
        <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-emerald-700">
          <BookOpen className="w-3 h-3" aria-hidden /> Suchtreffer
        </span>
        <span className="text-[10px] text-emerald-800">
          {data.rows.length} Treffer · {evaluatedCount} bewertet
        </span>
      </header>
      <ul className="divide-y divide-emerald-200">
        {rows.map((row, idx) => {
          const boxId = String((row.result.payload.box_id as string) ?? "");
          const score = Number((row.result.payload.score as number) ?? 0);
          const text = String((row.result.payload.text as string) ?? "");
          const boxKind = String((row.result.payload.box_kind as string) ?? "");
          const verdict = row.evaluation
            ? String((row.evaluation.payload.verdict as string) ?? "")
            : null;
          return (
            <li
              key={row.result.node_id}
              className="px-3 py-1.5 relative"
              style={{ minHeight: ROW_HEIGHT_PX }}
            >
              <div className="flex items-center gap-2 text-[10px]">
                <span className="font-mono text-emerald-800">{boxId}</span>
                <span className="text-emerald-700/70">
                  {score.toFixed(2)}
                </span>
                {boxKind && boxKind !== "paragraph" && (
                  <span
                    className={`px-1 rounded font-mono ${
                      boxKind === "table"
                        ? "bg-purple-100 text-purple-800"
                        : boxKind === "figure"
                          ? "bg-amber-100 text-amber-800"
                          : boxKind === "caption"
                            ? "bg-cyan-100 text-cyan-800"
                            : boxKind === "formula"
                              ? "bg-emerald-100 text-emerald-800"
                              : boxKind === "toc"
                                ? "bg-indigo-100 text-indigo-800"
                                : boxKind === "list_of_tables"
                                  ? "bg-purple-100 text-purple-800"
                                  : boxKind === "list_of_figures"
                                    ? "bg-amber-100 text-amber-800"
                                    : boxKind === "bibliography"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : "bg-canvas text-ink-muted"
                    }`}
                  >
                    {boxKind}
                  </span>
                )}
                {verdict && (
                  <span
                    className={`ml-auto px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wide ${
                      VERDICT_STYLE[verdict] ?? "bg-canvas text-ink-muted"
                    }`}
                  >
                    {verdict}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-ink line-clamp-1 mt-0.5">
                {text}
              </p>
              {/* Per-row source handle, anchored at the right edge so the
                  outgoing edge to a promoted chunk emerges from the row
                  itself rather than the tile bottom. */}
              <Handle
                type="source"
                position={Position.Right}
                id={`row-${row.result.node_id}`}
                className="!bg-purple-400 !w-2 !h-2 !border-purple-200"
                style={{ top: "50%", transform: "translateY(-50%)" }}
                isConnectable={false}
              />
              <RowIndex index={idx} />
            </li>
          );
        })}
        {data.rows.length > 10 && (
          <li className="px-3 py-1 text-[10px] italic text-emerald-700">
            … und {data.rows.length - 10} weitere
          </li>
        )}
      </ul>
    </div>
  );
}

/** Tiny marker so the user can pair side-panel rows with canvas rows. */
function RowIndex({ index }: { index: number }): JSX.Element {
  return (
    <span className="absolute top-1 right-2 text-[9px] text-emerald-700/50 font-mono">
      #{index + 1}
    </span>
  );
}

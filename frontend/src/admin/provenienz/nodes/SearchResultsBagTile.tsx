import { BookOpen } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { SearchResultsBagView } from "../layout";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-700 text-emerald-100",
  "partial-support": "bg-amber-600 text-amber-50",
  unrelated: "bg-slate-600 text-slate-200",
  contradicts: "bg-rose-700 text-rose-100",
  manual: "bg-purple-600 text-purple-100",
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
    <div className="rounded-lg border border-emerald-500 bg-emerald-800/90 text-white shadow-md w-80 relative">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-2 px-3 py-2 border-b border-emerald-600/60">
        <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-emerald-200">
          <BookOpen className="w-3 h-3" aria-hidden /> Suchtreffer
        </span>
        <span className="text-[10px] text-emerald-100">
          {data.rows.length} Treffer · {evaluatedCount} bewertet
        </span>
      </header>
      <ul className="divide-y divide-emerald-600/40">
        {rows.map((row, idx) => {
          const boxId = String((row.result.payload.box_id as string) ?? "");
          const score = Number((row.result.payload.score as number) ?? 0);
          const text = String((row.result.payload.text as string) ?? "");
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
                <span className="font-mono text-emerald-200">{boxId}</span>
                <span className="text-emerald-100/70">
                  {score.toFixed(2)}
                </span>
                {verdict && (
                  <span
                    className={`ml-auto px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wide ${
                      VERDICT_STYLE[verdict] ?? "bg-slate-600 text-slate-200"
                    }`}
                  >
                    {verdict}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-white/85 line-clamp-1 mt-0.5">
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
          <li className="px-3 py-1 text-[10px] italic text-emerald-200">
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
    <span className="absolute top-1 right-2 text-[9px] text-emerald-200/50 font-mono">
      #{index + 1}
    </span>
  );
}

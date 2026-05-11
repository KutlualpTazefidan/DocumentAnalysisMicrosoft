import { CornerDownRight } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { SearchResultTileView } from "../layout";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-700 text-emerald-100",
  "partial-support": "bg-amber-600 text-amber-50",
  unrelated: "bg-slate-600 text-slate-200",
  contradicts: "bg-rose-700 text-rose-100",
  manual: "bg-purple-600 text-purple-100",
};

/**
 * One search-result row pulled out of the bag because it has a
 * downstream plan_proposal or action_proposal anchored to it. Sits
 * between the bag and the plan/action chain so the audit trail is
 * connected end-to-end.
 */
export function SearchResultTile({
  data,
}: NodeProps<SearchResultTileView>): JSX.Element {
  const p = data.result.payload as {
    box_id?: string;
    score?: number;
    text?: string;
  };
  const evalNode = data.evaluation;
  const verdict = evalNode
    ? String((evalNode.payload as { verdict?: string }).verdict ?? "")
    : null;
  const boxId = String(p.box_id ?? "");
  const score = Number(p.score ?? 0);
  const text = String(p.text ?? "");
  return (
    <div className="rounded-lg border-2 border-cyan-500/70 bg-navy-800 px-3 py-2 text-white shadow-md w-72">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-cyan-200">
        <CornerDownRight className="w-3 h-3" aria-hidden />
        <span className="font-mono text-cyan-300">{boxId}</span>
        <span className="text-cyan-400/80">Score {score.toFixed(2)}</span>
        {verdict && (
          <span
            className={`ml-auto px-1.5 py-0.5 rounded text-[10px] uppercase ${
              VERDICT_STYLE[verdict] ?? "bg-slate-600 text-slate-200"
            }`}
          >
            {verdict}
          </span>
        )}
      </header>
      <p className="text-[12px] text-slate-200 mt-1 line-clamp-3">{text}</p>
      <p className="text-[10px] italic text-slate-500 mt-1">
        Klicken für Details + nächsten Schritt
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

import { Gavel } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { EvaluationView } from "../layout";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-50 text-emerald-800 border-emerald-500",
  "partial-support": "bg-amber-50 text-amber-800 border-amber-500",
  unrelated: "bg-slate-100 text-slate-700 border-slate-300",
  contradicts: "bg-rose-50 text-rose-800 border-rose-500",
  manual: "bg-purple-50 text-purple-800 border-purple-500",
  unknown: "bg-zinc-100 text-zinc-700 border-zinc-300",
};

/**
 * Evaluation Folge-Knoten — spawned by /decide on an evaluate
 * action_proposal. Shows the verdict + confidence inline; full
 * reasoning + per-sentence enumeration accessible via panel click.
 */
export function EvaluationTile({
  data,
}: NodeProps<EvaluationView>): JSX.Element {
  const p = data.evaluation.payload as {
    verdict?: string;
    confidence?: number;
    reasoning?: string;
    sentences?: { text: string; tag: string; why: string }[];
  };
  const verdict = String(p.verdict ?? "unknown");
  const confidence =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const reasoning = String(p.reasoning ?? "");
  const sentenceCount = Array.isArray(p.sentences) ? p.sentences.length : 0;
  const style = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.unknown;
  return (
    <div className={`prov-tile border-2 ${style} px-3 py-2 w-72`}>
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide opacity-90">
        <Gavel className="w-3 h-3" aria-hidden /> Bewertung
        {confidence !== null && (
          <span className="ml-auto opacity-80">{confidence}%</span>
        )}
      </header>
      <p className="text-[13px] font-semibold uppercase mt-1 tracking-wide">
        {verdict}
      </p>
      {reasoning && (
        <p className="text-[11px] italic line-clamp-3 mt-1 opacity-90">
          {reasoning}
        </p>
      )}
      {sentenceCount > 0 && (
        <p className="text-[10px] italic opacity-70 mt-1">
          {sentenceCount} Satz-Tags geprüft
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

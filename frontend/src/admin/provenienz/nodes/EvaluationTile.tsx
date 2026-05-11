import { Gavel } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { EvaluationView } from "../layout";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-700 text-emerald-100 border-emerald-500/70",
  "partial-support": "bg-amber-700 text-amber-50 border-amber-500/70",
  unrelated: "bg-slate-700 text-slate-200 border-slate-500/70",
  contradicts: "bg-rose-700 text-rose-100 border-rose-500/70",
  manual: "bg-purple-700 text-purple-100 border-purple-500/70",
  unknown: "bg-zinc-700 text-zinc-200 border-zinc-500/70",
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
    <div className={`rounded-lg border-2 ${style} px-3 py-2 shadow-md w-72`}>
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

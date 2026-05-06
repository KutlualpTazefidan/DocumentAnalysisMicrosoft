import { UserCheck } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ManualReviewView } from "../layout";

/**
 * Red-bordered tile: "the agent says only a human can resolve this."
 * Output of /next-step when neither a registered step nor a missing
 * capability would solve the problem — the agent escalates.
 */
export function ManualReviewTile({
  data,
}: NodeProps<ManualReviewView>): JSX.Element {
  const p = data.review.payload as {
    name?: string;
    description?: string;
    reasoning?: string;
  };
  return (
    <div className="rounded-lg border-2 border-rose-400 bg-rose-900/30 px-3 py-2 text-white shadow-md w-72">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-rose-200">
        <UserCheck className="w-3 h-3" aria-hidden /> Mensch-Aufgabe
      </header>
      {p.name && (
        <p className="text-sm font-semibold text-rose-50 mt-0.5">{p.name}</p>
      )}
      {p.description && (
        <p className="text-[11px] text-rose-100 mt-1 line-clamp-3">
          {p.description}
        </p>
      )}
      {p.reasoning && (
        <p className="text-[10px] text-rose-200/70 italic mt-1 line-clamp-2">
          Warum: {p.reasoning}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

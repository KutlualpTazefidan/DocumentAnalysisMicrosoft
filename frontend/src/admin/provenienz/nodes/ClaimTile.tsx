import { Lock, Quote, Target } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ClaimView } from "../layout";

/**
 * Single claim tile. Tasks live as their own tile downstream (no longer
 * folded into the claim). Per-claim research goal renders inline below
 * the claim text.
 */
export function ClaimTile({ data }: NodeProps<ClaimView>): JSX.Element {
  const text = String((data.claim.payload.text as string) ?? "");
  const claimGoal = String((data.claim.payload.goal as string) ?? "");
  const closed = !!data.closedByStop;

  return (
    <div className="rounded-lg border border-blue-500 bg-blue-700/90 px-3 py-2 text-white shadow-md w-64">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-blue-200">
        <Quote className="w-3 h-3" aria-hidden /> Aussage
      </header>
      <p className="text-xs leading-snug mt-1 line-clamp-3">{text}</p>
      {claimGoal && (
        <div className="mt-1.5 pt-1.5 border-t border-blue-400/30">
          <p className="flex items-center gap-1 text-[9px] uppercase tracking-wide text-pink-300">
            <Target className="w-3 h-3" aria-hidden /> Recherche-Frage
          </p>
          <p className="text-[11px] italic text-pink-100 line-clamp-2 mt-0.5">
            {claimGoal}
          </p>
        </div>
      )}
      {closed && (
        <p className="mt-1 text-[10px] text-amber-300 flex items-center gap-1">
          <Lock className="w-3 h-3" aria-hidden /> abgeschlossen
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

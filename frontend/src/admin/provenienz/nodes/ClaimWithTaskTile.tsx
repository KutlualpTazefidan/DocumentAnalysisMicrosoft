import { Lock, Quote, Search } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ClaimWithTaskView } from "../layout";

/**
 * Combines a claim with its (optional) formulated task. 1:1 by construction —
 * one claim has at most one task.
 */
export function ClaimWithTaskTile({
  data,
}: NodeProps<ClaimWithTaskView>): JSX.Element {
  const text = String((data.claim.payload.text as string) ?? "");
  const query = data.task
    ? String((data.task.payload.query as string) ?? "")
    : null;
  const closed = !!data.closedByStop;
  return (
    <div className="rounded-lg border border-blue-500 bg-blue-700/90 px-3 py-2 text-white shadow-md w-72">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-blue-200">
        <Quote className="w-3 h-3" aria-hidden /> Aussage
      </header>
      <p className="text-xs leading-snug mt-1 line-clamp-3">{text}</p>
      {query !== null && (
        <div className="mt-2 pt-2 border-t border-blue-400/40">
          <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-cyan-200">
            <Search className="w-3 h-3" aria-hidden /> Suchanfrage
          </header>
          <p className="text-xs italic mt-0.5 line-clamp-2">{query}</p>
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

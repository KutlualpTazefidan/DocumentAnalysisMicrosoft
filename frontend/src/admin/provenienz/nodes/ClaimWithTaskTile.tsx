import { BookOpen, CheckCircle2, Lock, Quote, Search } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ClaimWithTaskView } from "../layout";

/**
 * Combines a claim with its (optional) formulated task. 1:1 by construction.
 * Footer summarises downstream state: search-result count + evaluated count.
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
      <footer className="mt-1.5 flex items-center gap-2 text-[10px] text-blue-100/85">
        {data.task === undefined && (
          <span className="italic text-blue-200/75">
            keine Suchanfrage formuliert
          </span>
        )}
        {data.task !== undefined && data.searchResultCount === 0 && (
          <span className="italic text-blue-200/75">noch nicht gesucht</span>
        )}
        {data.searchResultCount > 0 && (
          <>
            <span className="flex items-center gap-1">
              <BookOpen className="w-3 h-3" aria-hidden />
              {data.searchResultCount} Treffer
            </span>
            {data.evaluatedCount > 0 && (
              <span className="flex items-center gap-1 text-rose-200">
                <CheckCircle2 className="w-3 h-3" aria-hidden />
                {data.evaluatedCount} bewertet
              </span>
            )}
          </>
        )}
        {closed && (
          <span className="ml-auto text-amber-300 flex items-center gap-1">
            <Lock className="w-3 h-3" aria-hidden /> abgeschlossen
          </span>
        )}
      </footer>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

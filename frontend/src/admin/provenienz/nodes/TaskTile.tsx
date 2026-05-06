import { Search } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { TaskView } from "../layout";

/**
 * Task tile — the search query formulated for a specific claim. Sits in
 * the trunk between the claim and the search-results bag.
 */
export function TaskTile({ data }: NodeProps<TaskView>): JSX.Element {
  const query = String((data.task.payload.query as string) ?? "");
  return (
    <div className="rounded-lg border border-cyan-500 bg-cyan-800/90 px-3 py-2 text-white shadow-md w-60">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-cyan-200">
        <Search className="w-3 h-3" aria-hidden /> Aufgabe
      </header>
      <p className="text-xs leading-snug mt-1 italic line-clamp-3">{query}</p>
      <p className="mt-1 text-[10px] text-cyan-200/80">
        {data.hasResults ? "Suchtreffer vorhanden" : "noch nicht gesucht"}
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

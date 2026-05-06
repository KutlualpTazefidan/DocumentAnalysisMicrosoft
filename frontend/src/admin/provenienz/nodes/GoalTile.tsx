import { Pencil, Target } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { GoalView } from "../layout";

/**
 * Top-of-canvas tile that displays the session's research goal. A
 * synthesised view (not a real Node in events.jsonl) — reads
 * SessionMeta.goal which is auto-extracted after the first claim or
 * editable manually via the side panel that opens on click.
 */
export function GoalTile({ data, selected }: NodeProps<GoalView>): JSX.Element {
  const empty = !data.text.trim();
  return (
    <div
      className={`rounded-lg border-2 px-4 py-2 text-white shadow-md w-96 ${
        empty
          ? "border-pink-700/60 bg-navy-800/60"
          : "border-pink-500 bg-pink-900/40"
      } ${selected ? "ring-2 ring-pink-300/60" : ""}`}
    >
      <header className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-pink-300">
          <Target className="w-3.5 h-3.5" aria-hidden /> Recherche-Ziel
        </p>
        <Pencil
          className="w-3.5 h-3.5 text-pink-300/60 group-hover:text-pink-200"
          aria-hidden
        />
      </header>
      {empty ? (
        <p className="text-sm text-slate-400 italic mt-1">
          noch nicht gesetzt — wird nach erster Aussage automatisch abgeleitet.
          Klick zum Bearbeiten.
        </p>
      ) : (
        <p className="text-sm text-pink-50 mt-1 line-clamp-3">{data.text}</p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

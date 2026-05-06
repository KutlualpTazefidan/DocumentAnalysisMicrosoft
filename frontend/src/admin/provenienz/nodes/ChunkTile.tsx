import { CornerDownRight, FileText, Lock, Quote } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ChunkView } from "../layout";

/**
 * Root tile of a session — the source-document chunk the user picked.
 * Promoted chunks (created via "Weiter erforschen" on a search result row)
 * render with a small purple "abgeleitet" marker.
 */
export function ChunkTile({ data }: NodeProps<ChunkView>): JSX.Element {
  const text = String((data.chunk.payload.text as string) ?? "");
  const boxId = String((data.chunk.payload.box_id as string) ?? "");
  const closed = !!data.closedByStop;
  const promoted = data.promoted;
  const claimCount = data.claimCount;

  return (
    <div
      className={`rounded-lg border px-3 py-2 text-white shadow-md w-64 ${
        promoted
          ? "border-purple-400 bg-slate-700"
          : "border-slate-500 bg-slate-700"
      }`}
    >
      <Handle
        type="target"
        position={promoted ? Position.Left : Position.Top}
        className="opacity-0"
      />
      <header className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-slate-300">
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" aria-hidden />
          {promoted ? "Chunk · abgeleitet" : "Chunk"}
        </span>
        {boxId && (
          <span className="font-mono text-blue-300 bg-navy-900/60 px-1 rounded">
            {boxId}
          </span>
        )}
      </header>
      {promoted && (
        <p className="mt-0.5 text-[10px] text-purple-300 flex items-center gap-1">
          <CornerDownRight className="w-3 h-3" aria-hidden />
          aus einem Suchtreffer abgeleitet
        </p>
      )}
      <p className="text-xs leading-snug mt-1 line-clamp-3">{text}</p>
      <footer className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-300/85">
        {claimCount > 0 ? (
          <span className="flex items-center gap-1">
            <Quote className="w-3 h-3" aria-hidden />
            {claimCount} Aussage{claimCount === 1 ? "" : "n"} extrahiert
          </span>
        ) : (
          <span className="italic text-slate-400/75">noch nicht analysiert</span>
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

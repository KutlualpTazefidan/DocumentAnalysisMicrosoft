import { FileText, Lock } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ChunkView } from "../layout";

/**
 * Root tile of a session — the source-document chunk the user picked.
 */
export function ChunkTile({ data }: NodeProps<ChunkView>): JSX.Element {
  const text = String((data.chunk.payload.text as string) ?? "");
  const boxId = String((data.chunk.payload.box_id as string) ?? "");
  const closed = !!data.closedByStop;
  return (
    <div className="rounded-lg border border-slate-500 bg-slate-700 px-3 py-2 text-white shadow-md w-64">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-slate-300">
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" aria-hidden /> Chunk
        </span>
        {boxId && (
          <span className="font-mono text-blue-300 bg-navy-900/60 px-1 rounded">
            {boxId}
          </span>
        )}
      </header>
      <p className="text-xs leading-snug mt-1 line-clamp-3">{text}</p>
      {closed && (
        <p className="mt-1 text-[10px] text-amber-300 flex items-center gap-1">
          <Lock className="w-3 h-3" aria-hidden /> abgeschlossen
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

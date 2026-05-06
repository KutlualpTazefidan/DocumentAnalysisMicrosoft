import { BookOpen } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function SearchResultNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const boxId = String(payload.box_id ?? "");
  const text = String(payload.text ?? "");
  const score = payload.score;
  const scoreLabel =
    typeof score === "number" ? `score: ${score.toFixed(2)}` : null;
  return (
    <div className="rounded border border-emerald-500 bg-emerald-800 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-emerald-200">
        <BookOpen className="w-3 h-3" aria-hidden /> search_result
      </header>
      {boxId && (
        <p className="text-[10px] font-mono text-emerald-100 mt-1">{boxId}</p>
      )}
      <p className="text-xs leading-tight line-clamp-2">{text}</p>
      {scoreLabel && (
        <p className="text-[10px] text-emerald-200 mt-1">{scoreLabel}</p>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

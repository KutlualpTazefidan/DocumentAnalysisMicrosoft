import { FileText } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function ChunkNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const text = String(payload.text ?? "");
  return (
    <div className="rounded border border-slate-500 bg-slate-700 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-300">
        <FileText className="w-3 h-3" aria-hidden /> chunk
      </header>
      <p className="text-xs leading-tight mt-1 line-clamp-3">{text}</p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

import { Search } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function TaskNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const query = String(payload.query ?? "");
  return (
    <div className="rounded border border-cyan-500 bg-cyan-800 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-cyan-200">
        <Search className="w-3 h-3" aria-hidden /> task
      </header>
      <p className="text-[10px] text-cyan-200 mt-1">Suchanfrage:</p>
      <p className="text-xs leading-tight line-clamp-2">{query}</p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

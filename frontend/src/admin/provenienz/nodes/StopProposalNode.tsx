import { OctagonAlert } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function StopProposalNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const reason = String(payload.reason ?? "");
  const closeSession = Boolean(payload.close_session);
  return (
    <div className="rounded border border-zinc-500 bg-zinc-700 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-zinc-300">
        <OctagonAlert className="w-3 h-3" aria-hidden /> stop_proposal
      </header>
      <p className="text-xs leading-tight mt-1 line-clamp-2">{reason}</p>
      <p className="text-[10px] text-zinc-300 mt-1">
        close_session: {closeSession ? "ja" : "nein"}
      </p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

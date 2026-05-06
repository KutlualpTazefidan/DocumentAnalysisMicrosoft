import { Lightbulb } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function ActionProposalNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const stepKind = String(payload.step_kind ?? "action_proposal");
  const recommended = payload.recommended as
    | { label?: string }
    | undefined;
  const recommendedLabel = recommended?.label ?? "";
  const alternatives = Array.isArray(payload.alternatives)
    ? payload.alternatives
    : [];
  const guidance = Array.isArray(payload.guidance_consulted)
    ? payload.guidance_consulted
    : [];
  return (
    <div className="rounded border border-amber-500 bg-amber-700 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-amber-100">
        <Lightbulb className="w-3 h-3" aria-hidden /> {stepKind}
      </header>
      <p className="text-xs leading-tight mt-1 line-clamp-2">
        {recommendedLabel}
      </p>
      <div className="flex gap-1 mt-1 flex-wrap">
        <span className="text-[10px] px-1 rounded bg-amber-900/60 text-amber-100">
          {alternatives.length} alt
        </span>
        <span className="text-[10px] px-1 rounded bg-amber-900/60 text-amber-100">
          {guidance.length} guide
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

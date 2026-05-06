import { Scale } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

function verdictColor(verdict: string): string {
  const v = verdict.toLowerCase();
  if (v.includes("support") || v === "ok" || v === "pass" || v === "true") {
    return "text-emerald-300";
  }
  if (v.includes("partial") || v.includes("unclear") || v === "warn") {
    return "text-amber-300";
  }
  if (v.includes("contradict") || v.includes("refute") || v === "fail" || v === "false") {
    return "text-red-300";
  }
  return "text-rose-100";
}

export function EvaluationNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const verdict = String(payload.verdict ?? "");
  const confidence = payload.confidence;
  const reasoning = payload.reasoning ? String(payload.reasoning) : null;
  const confLabel =
    typeof confidence === "number" ? `confidence: ${confidence.toFixed(2)}` : null;
  return (
    <div className="rounded border border-rose-500 bg-rose-800 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-rose-200">
        <Scale className="w-3 h-3" aria-hidden /> evaluation
      </header>
      <p className={`text-xs leading-tight mt-1 font-semibold ${verdictColor(verdict)}`}>
        {verdict}
      </p>
      {confLabel && (
        <p className="text-[10px] text-rose-100 mt-1">{confLabel}</p>
      )}
      {reasoning && (
        <p className="text-[10px] leading-tight text-rose-100 mt-1 line-clamp-2">
          {reasoning}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

import { UserCog } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ExpertCorrectionView } from "../layout";

/**
 * Sibling tile of a plan_proposal — the human expert prescribed a
 * different step. Renders red/rose so the override is visually
 * distinguishable from the agent's amber plan_proposal at a glance.
 * When the intended_step is not in the backend's _KNOWN_STEPS set the
 * tile also surfaces an "auch als Wunsch hinterlegt" badge so reviewers
 * see that an associated capability_request was spawned.
 *
 * Connected to its plan_proposal via a dashed "stattdessen" edge —
 * see Canvas.tsx for the edge rendering and layout.ts §5b for the view
 * builder.
 */
export function ExpertCorrectionTile({
  data,
}: NodeProps<ExpertCorrectionView>): JSX.Element {
  const p = data.correction.payload as {
    intended_step?: string;
    reason?: string;
    target_step_kind?: string;
    is_unimplemented?: boolean;
  };
  return (
    <div className="rounded-lg border-2 border-rose-500/80 bg-rose-900/40 px-3 py-2 text-white shadow-md w-[272px]">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-rose-200">
        <UserCog className="w-3 h-3" aria-hidden /> Korrektur
      </header>
      {p.intended_step && (
        <p className="text-sm font-semibold text-rose-50 font-mono mt-0.5 truncate">
          {p.intended_step}
        </p>
      )}
      {p.target_step_kind && (
        <p className="text-[10px] text-rose-300/80 mt-0.5">
          statt <span className="font-mono">{p.target_step_kind}</span>
        </p>
      )}
      {p.reason && (
        <p className="text-[11px] text-rose-100 mt-1 line-clamp-2">{p.reason}</p>
      )}
      {p.is_unimplemented && (
        <p className="text-[10px] text-amber-300 italic mt-1">
          auch als Wunsch hinterlegt
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

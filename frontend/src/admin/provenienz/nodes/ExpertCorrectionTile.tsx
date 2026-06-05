import { AlertTriangle, UserCog } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type {
  ExpertCorrectionView,
  ExpertMethodRequestView,
  ExpertStepOverrideView,
} from "../layout";

type AnyOverrideView =
  | ExpertStepOverrideView
  | ExpertMethodRequestView
  | ExpertCorrectionView;

/**
 * Phase-3 sibling tile of a plan_proposal — the human expert prescribed
 * a different step. One component renders all three view kinds:
 *
 *   • expert_step_override (Purpose 1 — teach the agent): rose accent,
 *     UserCog icon, "Korrektur" label.
 *   • expert_method_request (Purpose 2 — mark a capability gap):
 *     amber accent, AlertTriangle icon, "Neue Methode" label + the
 *     "landet auf der Capability-Wunschliste" badge.
 *   • Deprecated expert_correction (pre-Phase-3 / aliased legacy data):
 *     falls back to the Phase-1 rose styling, with the
 *     `payload.is_unimplemented` flag still surfacing the legacy "auch
 *     als Wunsch hinterlegt" hint.
 *
 * The tile is registered under all three Node-Kinds in `nodeTypes`
 * (see `./index.ts`), so the layout walker can emit any of the three
 * kinds and ReactFlow renders the right shape.
 *
 * Connected to its plan_proposal via a dashed "stattdessen" edge — see
 * Canvas.tsx for the edge rendering and layout.ts §5b for the view
 * builder.
 */
export function ExpertCorrectionTile({
  data,
}: NodeProps<AnyOverrideView>): JSX.Element {
  const p = data.correction.payload as {
    intended_step?: string;
    reason?: string;
    target_step_kind?: string;
    is_unimplemented?: boolean;
  };
  // Discriminator: the new Phase-3 kinds carry their semantics in
  // data.kind directly. The deprecated expert_correction kind falls
  // back to the legacy payload flag so aliased pre-Phase-3 data still
  // renders the right shape.
  const isMethodRequest =
    data.kind === "expert_method_request" ||
    (data.kind === "expert_correction" && p.is_unimplemented === true);

  const accent = isMethodRequest
    ? {
        border: "border-amber-500",
        bg: "bg-amber-50",
        headerText: "text-amber-800",
        title: "Neue Methode",
        stepText: "text-amber-900",
        subText: "text-amber-700/80",
        bodyText: "text-amber-900",
        Icon: AlertTriangle,
      }
    : {
        border: "border-rose-500",
        bg: "bg-rose-50",
        headerText: "text-rose-800",
        title: "Korrektur",
        stepText: "text-rose-900",
        subText: "text-rose-700/80",
        bodyText: "text-rose-900",
        Icon: UserCog,
      };
  const Icon = accent.Icon;

  return (
    <div
      className={`prov-tile border-2 ${accent.border} ${accent.bg} px-3 py-2 text-ink w-[272px]`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header
        className={`flex items-center gap-1 text-[10px] uppercase tracking-wide ${accent.headerText}`}
      >
        <Icon className="w-3 h-3" aria-hidden /> {accent.title}
      </header>
      {p.intended_step && (
        <p
          className={`text-sm font-semibold ${accent.stepText} font-mono mt-0.5 truncate`}
        >
          {p.intended_step}
        </p>
      )}
      {p.target_step_kind && (
        <p className={`text-[10px] ${accent.subText} mt-0.5`}>
          statt <span className="font-mono">{p.target_step_kind}</span>
        </p>
      )}
      {p.reason && (
        <p className={`text-[11px] ${accent.bodyText} mt-1 line-clamp-2`}>
          {p.reason}
        </p>
      )}
      {isMethodRequest && (
        <p className="text-[10px] text-amber-700 italic mt-1">
          landet auf der Capability-Wunschliste
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

/**
 * Read-only inspector for the expert_correction tile.
 *
 * Phase-1 surface: shows what the expert prescribed plus the rationale.
 * Editing/retraction lives in a later phase — for now the override is
 * append-only, and the matching capability_request (if the intended_step
 * was unimplemented) is visible by clicking through to its tile.
 */
export function ExpertCorrectionPanel({
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "expert_correction") return <></>;
  const node = view.correction;
  const p = node.payload as {
    intended_step?: string;
    intended_args?: Record<string, unknown>;
    reason?: string;
    target_proposal_node_id?: string;
    target_step_kind?: string;
    is_unimplemented?: boolean;
  };
  const argsAsJson = p.intended_args && Object.keys(p.intended_args).length > 0
    ? JSON.stringify(p.intended_args, null, 2)
    : "";

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Korrektur"
        subtitle={p.target_step_kind ? `statt ${p.target_step_kind}` : "—"}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Vorgeschlagener Schritt</p>
          <p className={`text-rose-300 ${T.body} font-mono`}>
            {p.intended_step || "—"}
          </p>
          {p.is_unimplemented && (
            <p className={`${T.tiny} text-amber-300 italic mt-1`}>
              Dieser Schritt ist (noch) nicht im Registry — er wurde
              parallel als Capability-Wunsch hinterlegt.
            </p>
          )}
        </div>
        {p.reason && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {p.reason}
            </p>
          </div>
        )}
        {argsAsJson && (
          <div>
            <p className={T.tinyBold}>Argumente</p>
            <pre className="text-[11px] text-slate-300 bg-chrome2-900 border border-chrome2-500 rounded px-2 py-1.5 overflow-x-auto">
              {argsAsJson}
            </pre>
          </div>
        )}
        <p className={`${T.tiny} text-slate-500 italic`}>
          Erfasst über „Verwerfen → Lieber so" am ursprünglichen
          Agent-Vorschlag. Die Korrektur landet als NOTE-Skill im Korpus
          und steht beim nächsten /next-step-Lauf als „Frühere
          Korrektur" zur Verfügung.
        </p>
      </div>
    </div>
  );
}

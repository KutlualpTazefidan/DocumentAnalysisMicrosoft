import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

/**
 * Read-only inspector for the expert-override tile (Phase-3 split:
 * expert_step_override + expert_method_request + the deprecated legacy
 * expert_correction shape). Renders kind-aware copy + accent so the
 * panel reads either as "Lieber dieser Step" (Purpose 1) or as "Neue
 * Methode gewünscht" (Purpose 2 — capability gap).
 *
 * Editing/retraction is out of scope; the override is append-only, and
 * the matching wishlist entry surfaces in the agent-wide
 * Capability-Wishlist (Phase 4) via the /capability-requests
 * aggregator that now also reads expert_method_request payloads.
 */
export function ExpertCorrectionPanel({
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (
    view.kind !== "expert_step_override" &&
    view.kind !== "expert_method_request" &&
    view.kind !== "expert_correction"
  ) {
    return <></>;
  }
  const node = view.correction;
  const p = node.payload as {
    intended_step?: string;
    intended_args?: Record<string, unknown>;
    reason?: string;
    target_proposal_node_id?: string;
    target_step_kind?: string;
    // Legacy Phase-1 marker — present on aliased Nodes from before
    // Phase-3 + on the deprecated expert_correction kind. The
    // post-Phase-3 path drops it; the Node.kind discriminates.
    is_unimplemented?: boolean;
  };
  // Treat the new kind as the primary discriminator, falling back to
  // the legacy payload flag when an aliased Node is shown. Both paths
  // converge on the same isMethodRequest signal.
  const isMethodRequest =
    view.kind === "expert_method_request" ||
    (view.kind === "expert_correction" && p.is_unimplemented === true);
  const argsAsJson =
    p.intended_args && Object.keys(p.intended_args).length > 0
      ? JSON.stringify(p.intended_args, null, 2)
      : "";

  const title = isMethodRequest ? "Methoden-Wunsch" : "Korrektur";
  const subtitle = p.target_step_kind ? `statt ${p.target_step_kind}` : "—";
  const stepAccent = isMethodRequest ? "text-amber-700" : "text-rose-700";

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title={title}
        subtitle={subtitle}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>
            {isMethodRequest ? "Gewünschte Methode" : "Vorgeschlagener Schritt"}
          </p>
          <p className={`${stepAccent} ${T.body} font-mono`}>
            {p.intended_step || "—"}
          </p>
          {isMethodRequest && (
            <p className={`${T.tiny} text-amber-700 italic mt-1`}>
              Diese Methode existiert noch nicht — sie landet in der
              Capability-Wunschliste, sodass das Team sie bauen kann.
            </p>
          )}
        </div>
        {p.reason && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-ink ${T.body} whitespace-pre-wrap`}>
              {p.reason}
            </p>
          </div>
        )}
        {argsAsJson && (
          <div>
            <p className={T.tinyBold}>Argumente</p>
            <pre className="text-[11px] text-ink-muted bg-canvas border border-line rounded px-2 py-1.5 overflow-x-auto">
              {argsAsJson}
            </pre>
          </div>
        )}
        <p className={`${T.tiny} text-ink-muted italic`}>
          {isMethodRequest
            ? `Erfasst über „Verwerfen → Lieber so“ mit einer Methode, die noch nicht im Registry steht. Der Wunsch landet zentral auf der Capability-Wunschliste.`
            : `Erfasst über „Verwerfen → Lieber so“ am ursprünglichen Agent-Vorschlag. Die Korrektur landet als NOTE-Skill im Korpus und steht beim nächsten /next-step-Lauf als „Frühere Korrektur“ zur Verfügung.`}
        </p>
      </div>
    </div>
  );
}

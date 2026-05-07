import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { AgentAuditSection } from "./AgentAuditSection";

const ASSESSMENT_LABEL: Record<string, string> = {
  vollständig: "✓ Bewertung wirkt vollständig",
  lückenhaft: "⚠ Lücken erkannt",
  fehlerhaft: "✗ Fehler in der Bewertung",
};

const RECOMMENDATION_LABEL: Record<string, string> = {
  accept: "Bewertung akzeptieren — keine Änderung nötig",
  "re-evaluate": "Erneut bewerten — mit Fokus auf die Lücken",
  "expand-context": "Zusätzlichen Kontext (Nachbarchunks) heranziehen",
};

/**
 * Side-panel for a reflection (self-critique) node. Shows the
 * assessment, missed statements, concerns, and recommendation. The
 * recommendation can be acted on by the user — re-evaluate triggers
 * the matching action_proposal flow with the missed statements
 * injected as additional context (handled in a follow-up commit).
 */
export function ReflectionPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "reflection") return <></>;
  const node = view.reflection;
  const p = node.payload as {
    self_assessment?: string;
    missed_statements?: string[];
    concerns?: string[];
    recommendation?: string;
    recommended_focus?: string;
    step_kind_reviewed?: string;
    audit?: Parameters<typeof AgentAuditSection>[0]["audit"];
  };
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();

  const assessment = String(p.self_assessment ?? "vollständig");
  const recommendation = String(p.recommendation ?? "accept");
  const missed = Array.isArray(p.missed_statements) ? p.missed_statements : [];
  const concerns = Array.isArray(p.concerns) ? p.concerns : [];
  const focus = String(p.recommended_focus ?? "");

  async function handleDelete(): Promise<void> {
    if (!window.confirm("Reflektion verwerfen?")) return;
    try {
      await del.mutateAsync(node.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Reflektion"
        subtitle={
          ASSESSMENT_LABEL[assessment] ?? `Selbst-Bewertung: ${assessment}`
        }
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Empfehlung</p>
          <p className={`text-violet-200 ${T.body}`}>
            {RECOMMENDATION_LABEL[recommendation] ?? recommendation}
          </p>
          {focus && (
            <p className={`text-slate-400 ${T.body} italic mt-1`}>
              Fokus: „{focus}"
            </p>
          )}
        </div>
        {concerns.length > 0 && (
          <div>
            <p className={T.tinyBold}>Bedenken</p>
            <ul className="mt-1 space-y-1">
              {concerns.map((c, i) => (
                <li
                  key={i}
                  className={`text-amber-200 ${T.body} italic`}
                >
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
        {missed.length > 0 && (
          <div>
            <p className={T.tinyBold}>Übersehene Sätze</p>
            <ul className="mt-1 space-y-1">
              {missed.map((m, i) => (
                <li
                  key={i}
                  className={`text-rose-200 ${T.body} rounded bg-rose-900/30 px-2 py-1`}
                >
                  „{m}"
                </li>
              ))}
            </ul>
          </div>
        )}
        <AgentAuditSection audit={p.audit} />
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <p className={`${T.tiny} text-slate-500 italic`}>
          Re-Evaluate-Aktion mit injiziertem Fokus folgt im nächsten
          Build-Schritt — derzeit dient die Reflektion als Audit-Eintrag
          + Hinweis für manuelle Re-Evaluation.
        </p>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-rose-700 text-rose-300 hover:bg-rose-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Reflektion verwerfen"}
        </button>
      </footer>
    </div>
  );
}

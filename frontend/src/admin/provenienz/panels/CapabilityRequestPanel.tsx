import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { AgentAuditSection } from "./AgentAuditSection";

/**
 * Read-mostly panel for a capability_request tile. The agent is saying
 * "we need a capability that doesn't exist yet" — typically a tool, a
 * parser, an external API, etc. The user can dismiss it (tombstone) or
 * leave it in the canvas as a TODO marker.
 */
export function CapabilityRequestPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "capability_request") return <></>;
  const node = view.request;
  const p = node.payload as {
    name?: string;
    description?: string;
    reasoning?: string;
    considered_alternatives?: { name: string; kind: string; why_not: string }[];
    confidence?: number;
    audit?: Parameters<typeof AgentAuditSection>[0]["audit"];
  };
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();
  const conf =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const alts = Array.isArray(p.considered_alternatives)
    ? p.considered_alternatives
    : [];

  async function handleDismiss(): Promise<void> {
    if (!window.confirm("Capability-Vermerk verwerfen?")) return;
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
        title="Fehlende Capability"
        subtitle={p.name || "—"}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {conf !== null && (
          <div>
            <p className={T.tinyBold}>Konfidenz</p>
            <p className={`text-yellow-300 ${T.body} font-mono`}>{conf}%</p>
          </div>
        )}
        {p.description && (
          <div>
            <p className={T.tinyBold}>Was fehlt</p>
            <p className={`text-yellow-100 ${T.body} whitespace-pre-wrap`}>
              {p.description}
            </p>
          </div>
        )}
        {p.reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung des Agenten</p>
            <p className={`text-slate-200 ${T.body} italic whitespace-pre-wrap`}>
              {p.reasoning}
            </p>
          </div>
        )}
        {alts.length > 0 && (
          <div>
            <p className={T.tinyBold}>Erwogene Alternativen</p>
            <ul className="mt-1 space-y-1.5">
              {alts.map((a, i) => (
                <li
                  key={i}
                  className="rounded border border-navy-700 bg-navy-900/50 px-2 py-1.5"
                >
                  <p className={`${T.body} text-slate-200`}>
                    <span className="font-mono text-yellow-300">{a.name}</span>{" "}
                    <span className="text-slate-500">({a.kind})</span>
                  </p>
                  {a.why_not && (
                    <p className={`${T.tiny} text-slate-400 italic mt-0.5`}>
                      Nicht gewählt weil: {a.why_not}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <AgentAuditSection audit={p.audit} />
        <p className={`${T.tiny} text-slate-500 italic`}>
          Capability-Vermerke sammeln sich als TODO-Liste für künftige
          Tool-/Skill-Entwicklung. Verwerfen löscht den Eintrag aus dem
          Canvas (bleibt im Audit-Log).
        </p>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleDismiss()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-yellow-700 text-yellow-300 hover:bg-yellow-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Vermerk verwerfen"}
        </button>
      </footer>
    </div>
  );
}

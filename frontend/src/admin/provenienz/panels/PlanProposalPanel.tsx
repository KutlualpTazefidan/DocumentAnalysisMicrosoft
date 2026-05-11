import { useToast } from "../../../shared/components/useToast";
import {
  useDecomposeHit,
  useDeleteNode,
  useEvaluate,
  useExtractClaims,
  useFormulateTask,
  useInvestigateTable,
  useProposeStop,
  usePromoteSearchResult,
  useSearchStep,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { AgentAuditSection } from "./AgentAuditSection";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
  promote_search_result: "Treffer vertiefen",
  decompose_hit: "Treffer zerlegen",
  investigate_table: "Tabellen-Untersuchung",
};

/**
 * Side-panel for a plan_proposal tile from /next-step. Shows the agent's
 * picked step + reasoning + considered alternatives. "Akzeptieren" fires
 * the matching step route AND keeps the plan_proposal tile in the canvas
 * — the audit trail is the point of Provenienz, the resulting
 * action_proposal renders alongside it. User can manually "Verwerfen"
 * to tombstone if a tile turned out to be noise.
 */
export function PlanProposalPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "plan_proposal") return <></>;
  const node = view.plan;
  const p = node.payload as {
    name: string;
    description: string;
    reasoning: string;
    considered_alternatives: { name: string; kind: string; why_not: string }[];
    confidence: number;
    tool: string | null;
    approach_id: string | null;
    anchor_node_id: string;
    /** Click-trail persisted by the planner when the run was invoked
     *  from a Folge-Knoten (e.g. Bewertungs-Tile). The accept-handler
     *  forwards it to the underlying step mutation so the trail
     *  propagates plan → action_proposal → spawned nodes. */
    triggered_from_node_id?: string;
    audit?: {
      source_label?: string;
      system_prompt_used?: string;
      input_summary?: {
        anchor_kind?: string;
        anchor_text_preview?: string;
        session_goal?: string;
        available_steps?: string[];
        tools_summary?: string;
      };
      guidance_consulted?: { kind: string; id: string; summary: string }[];
    };
  };
  const extract = useExtractClaims(token, sessionId);
  const formulate = useFormulateTask(token, sessionId);
  const search = useSearchStep(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const evaluate = useEvaluate(token, sessionId);
  const promote = usePromoteSearchResult(token, sessionId);
  const decompose = useDecomposeHit(token, sessionId);
  const investigate = useInvestigateTable(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const { error: toastError, success: toastSuccess } = useToast();
  const isPending =
    extract.isPending ||
    formulate.isPending ||
    search.isPending ||
    stop.isPending ||
    evaluate.isPending ||
    promote.isPending ||
    decompose.isPending ||
    investigate.isPending ||
    del.isPending;

  async function handleAccept(): Promise<void> {
    // Forward the click-trail from the plan_proposal onto every step
    // mutation so the trail propagates plan → action_proposal → spawned
    // nodes (Trail-as-Trunk). Empty/undefined when this plan didn't
    // come from a Folge-Knoten — the step mutations omit the field
    // accordingly.
    const trail = p.triggered_from_node_id || undefined;
    try {
      switch (p.name) {
        case "extract_claims":
          await extract.mutateAsync({
            chunk_node_id: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "formulate_task":
          await formulate.mutateAsync({
            claim_node_id: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "search":
          await search.mutateAsync({
            task_node_id: p.anchor_node_id,
            top_k: 5,
            triggered_from_node_id: trail,
          });
          break;
        case "propose_stop":
          await stop.mutateAsync({
            anchor_node_id: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "evaluate":
          // Backend resolves against_claim_id from the search_result
          // chain (sr → task.focus_claim_id) when omitted.
          await evaluate.mutateAsync({
            search_result_node_id: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "promote_search_result":
          await promote.mutateAsync({
            searchResultNodeId: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "decompose_hit":
          await decompose.mutateAsync({
            searchResultNodeId: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          break;
        case "investigate_table": {
          const out = await investigate.mutateAsync({
            search_result_node_id: p.anchor_node_id,
            triggered_from_node_id: trail,
          });
          const skipped = out.skipped
            .map((s) => `${s.axis}: ${s.reason}`)
            .join(" | ");
          const msg =
            `${out.proposals.length} Vorschläge gespawnt` +
            (skipped ? ` — übersprungen: ${skipped}` : "");
          toastSuccess(msg);
          break;
        }
        default:
          toastError(`Unbekannter Schritt: ${p.name}`);
          return;
      }
      // Do NOT auto-delete the plan_proposal here. The audit trail is
      // the point of Provenienz: keep the tile visible alongside the
      // resulting action_proposal so reviewers see "agent suggested X
      // → step Y produced Z". Use "Verwerfen" below to tombstone an
      // individual proposal manually.
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDismiss(): Promise<void> {
    try {
      await del.mutateAsync(node.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  const conf = Math.round(p.confidence * 100);
  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Agent-Vorschlag"
        subtitle={STEP_LABEL[p.name] ?? p.name}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Empfohlener Schritt</p>
          <p className={`text-amber-300 ${T.body} font-mono`}>
            {p.name} <span className="text-amber-400">· {conf}%</span>
          </p>
        </div>
        {(p.tool || p.approach_id) && (
          <div className="flex gap-2">
            {p.tool && (
              <div className="flex-1">
                <p className={T.tinyBold}>Tool</p>
                <p className={`text-emerald-300 ${T.body}`}>{p.tool}</p>
              </div>
            )}
            {p.approach_id && (
              <div className="flex-1">
                <p className={T.tinyBold}>Approach</p>
                <p className={`text-purple-300 ${T.body}`}>{p.approach_id}</p>
              </div>
            )}
          </div>
        )}
        {p.reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {p.reasoning}
            </p>
          </div>
        )}
        <AgentAuditSection audit={p.audit} />
        {p.considered_alternatives.length > 0 && (
          <div>
            <p className={T.tinyBold}>Erwogene Alternativen</p>
            <ul className="mt-1 space-y-1.5">
              {p.considered_alternatives.map((a, i) => (
                <li
                  key={i}
                  className="rounded border border-navy-700 bg-navy-900/50 px-2 py-1.5"
                >
                  <p className={`${T.body} text-slate-200`}>
                    <span className="font-mono text-amber-300">{a.name}</span>{" "}
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
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleAccept()}
          disabled={isPending}
          className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} disabled:opacity-50`}
        >
          {isPending ? "…" : "Akzeptieren"}
        </button>
        <button
          type="button"
          onClick={() => void handleDismiss()}
          disabled={isPending}
          className={`w-full px-3 py-2 rounded border border-amber-700 text-amber-300 hover:bg-amber-900/30 ${T.body} disabled:opacity-50`}
        >
          Verwerfen
        </button>
      </footer>
    </div>
  );
}

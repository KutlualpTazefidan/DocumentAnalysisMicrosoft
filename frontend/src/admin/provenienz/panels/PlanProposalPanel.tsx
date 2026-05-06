import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useExtractClaims,
  useFormulateTask,
  useProposeStop,
  useSearchStep,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
  promote_search_result: "Treffer weiter erforschen",
  stop: "Sitzung stoppen",
};

/**
 * Side-panel detail for a Planner-Vorschlag tile in the canvas. Reads the
 * full plan payload (next_step, target_anchor, tool, approach, reasoning,
 * expected_outcome, fallback_plan, confidence). "Akzeptieren" auto-fires
 * the matching step route; "Verwerfen" tombstones the plan_proposal so
 * the tile vanishes. Both write to events.jsonl — full audit trail.
 */
export function PlanProposalPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "plan_proposal") return <></>;
  const node = view.proposal;
  const p = node.payload as {
    next_step: string;
    target_anchor_id: string;
    tool: string | null;
    approach_id: string | null;
    reasoning: string;
    expected_outcome: string;
    confidence: number;
    fallback_plan: string;
    guidance_consulted?: { kind: string; id: string; summary: string }[];
  };

  const extract = useExtractClaims(token, sessionId);
  const formulate = useFormulateTask(token, sessionId);
  const search = useSearchStep(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();
  const isPending =
    extract.isPending ||
    formulate.isPending ||
    search.isPending ||
    stop.isPending ||
    del.isPending;

  async function handleAccept(): Promise<void> {
    try {
      switch (p.next_step) {
        case "extract_claims":
          await extract.mutateAsync({ chunk_node_id: p.target_anchor_id });
          break;
        case "formulate_task":
          await formulate.mutateAsync({ claim_node_id: p.target_anchor_id });
          break;
        case "search":
          await search.mutateAsync({ task_node_id: p.target_anchor_id, top_k: 5 });
          break;
        case "propose_stop":
          await stop.mutateAsync({ anchor_node_id: p.target_anchor_id });
          break;
        case "evaluate":
          toastError(
            "Bewerten benötigt einen Claim als Bezug — bitte direkt auf der Trefferliste auswählen.",
          );
          return;
        case "promote_search_result":
          toastError(
            "Treffer weiter erforschen geht nur per Klick auf eine konkrete Trefferzeile.",
          );
          return;
        case "stop":
          // Just dismiss the plan; "stop" is informational.
          break;
        default:
          toastError(`Unbekannter Schritt: ${p.next_step}`);
          return;
      }
      await del.mutateAsync(node.node_id);
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

  const conf = typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const guidance = p.guidance_consulted ?? [];

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Planer-Vorschlag"
        subtitle={STEP_LABEL[p.next_step] ?? p.next_step}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Empfohlener Schritt</p>
          <p className={`text-amber-300 ${T.body} font-mono`}>
            {p.next_step} {conf !== null && <span className="text-amber-400">· {conf}%</span>}
          </p>
        </div>
        {p.target_anchor_id && (
          <div>
            <p className={T.tinyBold}>Ziel-Knoten</p>
            <p className={`text-slate-300 font-mono ${T.tiny}`}>{p.target_anchor_id}</p>
          </div>
        )}
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
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>{p.reasoning}</p>
          </div>
        )}
        {p.expected_outcome && (
          <div>
            <p className={T.tinyBold}>Erwartetes Ergebnis</p>
            <p className={`text-slate-200 ${T.body} italic`}>{p.expected_outcome}</p>
          </div>
        )}
        {p.fallback_plan && (
          <div>
            <p className={T.tinyBold}>Plan B</p>
            <p className={`text-slate-200 ${T.body}`}>{p.fallback_plan}</p>
          </div>
        )}
        {guidance.length > 0 && (
          <div>
            <p className={T.tinyBold}>Konsultierte Hinweise</p>
            <ul className="mt-1 space-y-1">
              {guidance.map((g, i) => (
                <li key={i} className={`${T.tiny} text-slate-300`}>
                  <span className={`px-1 py-0.5 rounded ${T.tiny} ${
                    g.kind === "approach"
                      ? "bg-purple-900/60 text-purple-200"
                      : "bg-amber-900/60 text-amber-200"
                  }`}>{g.kind}</span>{" "}
                  {g.summary}
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

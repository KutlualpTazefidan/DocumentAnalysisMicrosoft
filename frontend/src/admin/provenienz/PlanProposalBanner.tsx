import { Lightbulb, Sparkles, X } from "lucide-react";

import { useToast } from "../../shared/components/useToast";
import {
  useDeleteNode,
  useExtractClaims,
  useFormulateTask,
  useProposeStop,
  useSearchStep,
  type PlanProposal,
} from "../hooks/useProvenienz";
import { T } from "../styles/typography";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
  promote_search_result: "Treffer weiter erforschen",
  stop: "Sitzung stoppen",
};

interface Props {
  plan: PlanProposal;
  sessionId: string;
  token: string;
  onDismiss: () => void;
}

/**
 * Yellow banner at the top of the session canvas surfacing the latest
 * Planner recommendation. "Akzeptieren" auto-fires the matching step
 * route against the planner-chosen anchor — saves the user from clicking
 * through the underlying step manually.
 */
export function PlanProposalBanner({ plan, sessionId, token, onDismiss }: Props): JSX.Element {
  const p = plan.payload;
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
            "Bewerten benötigt zusätzlich einen Claim als Bezug — bitte manuell auf der Treffer-Liste auswählen.",
          );
          return;
        case "promote_search_result":
          toastError(
            "Treffer weiter erforschen geht nur per Klick auf eine konkrete Trefferzeile.",
          );
          return;
        case "stop":
          toastError("Stopp empfohlen — keine weitere automatische Aktion.");
          return;
        default:
          toastError(`Unbekannter Schritt: ${p.next_step}`);
          return;
      }
      // Plan accepted → drop the plan_proposal node so the banner
      // doesn't keep showing.
      await del.mutateAsync(plan.node_id);
      onDismiss();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleDismiss(): Promise<void> {
    try {
      await del.mutateAsync(plan.node_id);
    } catch {
      /* ignore */
    }
    onDismiss();
  }

  return (
    <div className="border-b-2 border-amber-500 bg-amber-900/20 px-4 py-2">
      <div className="flex items-start gap-3">
        <Sparkles className="w-5 h-5 text-amber-300 shrink-0 mt-0.5" aria-hidden />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className={`${T.tinyBold} text-amber-300`}>Planer-Vorschlag</p>
            <span className="text-amber-400 text-[10px]">
              Konfidenz {(p.confidence * 100).toFixed(0)}%
            </span>
            <span className="text-[10px] uppercase tracking-wide bg-amber-700 text-amber-50 px-1.5 py-0.5 rounded">
              {STEP_LABEL[p.next_step] ?? p.next_step}
            </span>
            {p.tool && (
              <span className="text-[10px] uppercase tracking-wide bg-emerald-700 text-emerald-50 px-1.5 py-0.5 rounded">
                🔧 {p.tool}
              </span>
            )}
            {p.approach_id && (
              <span className="text-[10px] uppercase tracking-wide bg-purple-700 text-purple-50 px-1.5 py-0.5 rounded">
                Approach: {p.approach_id}
              </span>
            )}
          </div>
          <p className={`${T.body} text-amber-100 mt-1`}>
            <Lightbulb className="w-3 h-3 inline mr-1" aria-hidden />
            {p.reasoning}
          </p>
          {p.expected_outcome && (
            <p className={`${T.tiny} text-amber-200/80 mt-0.5 italic`}>
              Erwartet: {p.expected_outcome}
            </p>
          )}
          {p.fallback_plan && (
            <p className={`${T.tiny} text-amber-200/80 mt-0.5`}>
              <span className="text-amber-300">Plan B:</span> {p.fallback_plan}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => void handleAccept()}
            disabled={isPending || p.next_step === "stop"}
            className={`px-3 py-1 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} disabled:opacity-50`}
          >
            {isPending ? "…" : "Akzeptieren"}
          </button>
          <button
            type="button"
            onClick={() => void handleDismiss()}
            className="p-1 rounded text-amber-300/70 hover:text-amber-200 hover:bg-amber-900/30"
            aria-label="Verwerfen"
            title="Verwerfen"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

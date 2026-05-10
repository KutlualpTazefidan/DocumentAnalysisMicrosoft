import { Sparkles } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useNextStepStream,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

const VERDICT_LABEL: Record<string, string> = {
  "likely-source": "stützt — wahrscheinliche Quelle",
  "partial-support": "stützt teilweise",
  unrelated: "nicht relevant",
  contradicts: "widerspricht",
  manual: "manuell vergeben",
  unknown: "unbekannt",
};

const TAG_STYLE: Record<string, string> = {
  STÜTZT: "bg-emerald-900/40 border-emerald-600 text-emerald-100",
  WIDERSPRICHT: "bg-rose-900/40 border-rose-600 text-rose-100",
  "NICHT-RELEVANT": "bg-slate-800/60 border-slate-600 text-slate-300",
};

/**
 * Evaluation Folge-Knoten Panel: full reasoning + per-sentence
 * enumeration from Phase A's EVALUATE_SYSTEM. Read-only view; the
 * evaluation Node is immutable once spawned (re-evaluate spawns a new
 * node rather than mutating).
 */
export function EvaluationPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "evaluation") return <></>;
  const node = view.evaluation;
  const p = node.payload as {
    verdict?: string;
    confidence?: number;
    reasoning?: string;
    sentences?: { text?: string; tag?: string; why?: string }[];
    capability_scan?: {
      approach_id?: string;
      name?: string;
      parent_capability?: string;
      matched?: boolean;
      reasons?: string[];
    }[];
    /** Deterministic-tool audit trail. Mirrors capability_scan but
     * for tools (Calculator, RegisterLookup, ...) instead of skills. */
    tool_calls?: {
      tool?: string;
      operation?: string;
      input?: Record<string, unknown>;
      output?: Record<string, unknown>;
    }[];
    search_result_node_id?: string;
  };
  const verdict = String(p.verdict ?? "unknown");
  const confidence =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const reasoning = String(p.reasoning ?? "");
  const sentences = Array.isArray(p.sentences) ? p.sentences : [];
  const capScan = Array.isArray(p.capability_scan) ? p.capability_scan : [];
  const capMatched = capScan.filter((c) => c.matched).length;
  const toolCalls = Array.isArray(p.tool_calls) ? p.tool_calls : [];
  // The parent search_result is the right anchor for "Was als nächstes?"
  // because decompose_hit / promote_search_result / re-evaluate are all
  // registered for search_result nodes, not for evaluation nodes. The
  // click target is the bewertung-tile but the pipeline runs against
  // the upstream hit.
  const parentSearchResultId = String(
    p.search_result_node_id ?? "",
  );
  const del = useDeleteNode(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  async function handleNextStep(): Promise<void> {
    if (!parentSearchResultId) {
      toastError(
        "Diese Bewertung kennt ihren Suchtreffer nicht — Re-Evaluierung " +
          "über das Suchtreffer-Tile starten.",
      );
      return;
    }
    // Forward the evaluation node_id as click-trail so the backend
    // (a) persists it on the spawned plan_proposal for the canvas
    // "triggered-from" edge and (b) tells the planner this run came
    // from a Bewertung — deepen the trace, don't re-evaluate.
    await stream.start(parentSearchResultId, {
      triggered_from_node_id: node.node_id,
    });
  }

  async function handleDelete(): Promise<void> {
    if (!window.confirm("Bewertung verwerfen?")) return;
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
        title="Bewertung"
        subtitle={VERDICT_LABEL[verdict] ?? verdict}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className={`flex items-baseline gap-2 ${T.body}`}>
          <span className="font-mono uppercase font-semibold text-slate-100">
            {verdict}
          </span>
          {confidence !== null && (
            <span className="text-slate-400">{confidence}% Konfidenz</span>
          )}
        </div>
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} italic mt-1`}>{reasoning}</p>
          </div>
        )}
        {toolCalls.length > 0 && (
          <details className="rounded border border-cyan-700/40 bg-cyan-950/10" open>
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-cyan-300 flex items-center gap-2`}
            >
              🛠 Werkzeug-Ergebnisse: {toolCalls.length}{" "}
              {toolCalls.length === 1 ? "Werkzeug" : "Werkzeuge"} ausgeführt
            </summary>
            <ul className="px-3 pb-3 pt-1 space-y-2">
              {toolCalls.map((tc, idx) => {
                const out = (tc.output ?? {}) as {
                  reasoning?: string;
                  any_match?: boolean;
                  n_matches?: number;
                  n_pairs?: number;
                  results?: { reasoning?: string; match?: boolean }[];
                };
                const inp = (tc.input ?? {}) as {
                  rel_tolerance?: number;
                  claim_quantities?: { value?: number; raw_unit?: string }[];
                  candidate_quantities?: { value?: number; raw_unit?: string }[];
                };
                return (
                  <li
                    key={idx}
                    className="rounded px-2 py-1.5 bg-cyan-900/20 border border-cyan-700/30"
                  >
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className={`font-mono ${T.body} text-cyan-200`}>
                        🛠 {tc.tool}
                      </span>
                      <span className={`${T.tiny} text-cyan-400/80 font-mono`}>
                        op={tc.operation}
                      </span>
                      {typeof inp.rel_tolerance === "number" && (
                        <span className={`${T.tiny} text-cyan-400/60`}>
                          Toleranz {(inp.rel_tolerance * 100).toFixed(2)}%
                        </span>
                      )}
                    </div>
                    {out.reasoning && (
                      <p className={`${T.tiny} text-cyan-100/90 mt-1`}>
                        {out.reasoning}
                      </p>
                    )}
                    {Array.isArray(out.results) && out.results.length > 0 && (
                      <ul className={`mt-1 space-y-0.5 ${T.tiny}`}>
                        {out.results.map((r, ri) => (
                          <li
                            key={ri}
                            className={
                              r.match
                                ? "text-emerald-200"
                                : "text-rose-200/80"
                            }
                          >
                            · {r.reasoning ?? ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </details>
        )}
        {capScan.length > 0 && (
          <details
            className="rounded border border-orange-700/40 bg-orange-950/10"
            open={capMatched > 0}
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-orange-300 flex items-center gap-2`}
            >
              🔧 Fähigkeiten-Scan: {capMatched}/{capScan.length}{" "}
              {capScan.length === 1 ? "Fähigkeit" : "Fähigkeiten"}{" "}
              getriggert
              {capMatched > 0 && (
                <span className="ml-auto text-emerald-300">
                  → Gate erstellt
                </span>
              )}
            </summary>
            <ul className="px-3 pb-3 pt-1 space-y-1.5">
              {capScan.map((c) => (
                <li
                  key={c.approach_id}
                  className={`rounded px-2 py-1.5 ${
                    c.matched
                      ? "bg-emerald-900/30 border border-emerald-700/50"
                      : "bg-navy-900/50 border border-navy-700"
                  }`}
                >
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span
                      className={`font-mono ${T.body} ${
                        c.matched ? "text-emerald-200" : "text-slate-400"
                      }`}
                    >
                      {c.matched ? "✓" : "○"} {c.name}
                    </span>
                    {c.parent_capability && (
                      <span
                        className={`${T.tiny} font-mono text-orange-300/80`}
                      >
                        ↳ {c.parent_capability}
                      </span>
                    )}
                  </div>
                  {c.reasons && c.reasons.length > 0 && (
                    <ul
                      className={`mt-1 space-y-0.5 ${T.tiny} ${
                        c.matched ? "text-emerald-200/80" : "text-slate-500"
                      }`}
                    >
                      {c.reasons.map((r, i) => (
                        <li key={i}>· {r}</li>
                      ))}
                    </ul>
                  )}
                  {!c.matched && (!c.reasons || c.reasons.length === 0) && (
                    <p className={`${T.tiny} text-slate-500 italic mt-1`}>
                      Keine Trigger konfiguriert.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
        {sentences.length > 0 && (
          <div>
            <p className={T.tinyBold}>Per-Satz-Analyse ({sentences.length})</p>
            <ul className="mt-1 space-y-1.5">
              {sentences.map((s, i) => {
                const tag = String(s.tag ?? "").toUpperCase();
                const tagStyle =
                  TAG_STYLE[tag] ?? "bg-zinc-800 border-zinc-600 text-zinc-200";
                return (
                  <li
                    key={i}
                    className={`rounded border px-2 py-1.5 ${tagStyle}`}
                  >
                    <p className={`${T.body} italic`}>„{s.text ?? ""}"</p>
                    <div
                      className={`flex items-center gap-2 mt-1 ${T.tiny}`}
                    >
                      <span className="font-mono font-semibold uppercase">
                        {tag}
                      </span>
                      <span className="opacity-80">{s.why ?? ""}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <LiveRunPanel
          run={stream}
          anchorPreview={reasoning.slice(0, 120)}
          onClose={() => stream.reset()}
        />
        <button
          type="button"
          onClick={() => void handleNextStep()}
          disabled={stream.isRunning || !parentSearchResultId}
          className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
          title="Agent fragt: was nun? (z.B. Treffer dekomponieren wenn er selbst Behauptungen enthält)"
        >
          <Sparkles className="w-4 h-4" aria-hidden />
          {stream.isRunning ? "Agent denkt…" : "Was als nächstes?"}
        </button>
        <p className={`${T.tiny} text-slate-500 italic`}>
          Bewertung ist immutable — re-evaluate erzeugt eine neue Bewertung
          als Folge-Knoten. „Was als nächstes?" arbeitet auf dem
          übergeordneten Suchtreffer (z.B. dekomponieren wenn er selbst
          Behauptungen enthält).
        </p>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-rose-700 text-rose-300 hover:bg-rose-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Bewertung verwerfen"}
        </button>
      </footer>
    </div>
  );
}

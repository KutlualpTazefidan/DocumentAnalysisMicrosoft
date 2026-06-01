import { useEffect, useMemo, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import {
  useAgentInfo,
  useDecide,
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
  const extract = useExtractClaims(token, sessionId);
  const formulate = useFormulateTask(token, sessionId);
  const search = useSearchStep(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const evaluate = useEvaluate(token, sessionId);
  const promote = usePromoteSearchResult(token, sessionId);
  const decompose = useDecomposeHit(token, sessionId);
  const investigate = useInvestigateTable(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const decide = useDecide(token, sessionId);
  const agentInfo = useAgentInfo(token);
  const [verwerfenMode, setVerwerfenMode] = useState<"idle" | "form">("idle");
  const [intendedStep, setIntendedStep] = useState("");
  const [reason, setReason] = useState("");
  // Post-hoc drawer (Phase-2): a permanent secondary footer for the
  // "I realised too late" case. Independent state from the Verwerfen-
  // morph so both forms can coexist visually without sharing inputs.
  // Submits the same /decide expert_correction body but with
  // ``post_hoc=true`` so audits can tell decision-time vs after-the-
  // fact corrections apart.
  const [postHocMode, setPostHocMode] = useState<"idle" | "form">("idle");
  const [postHocStep, setPostHocStep] = useState("");
  const [postHocReason, setPostHocReason] = useState("");
  const { error: toastError, success: toastSuccess } = useToast();
  // Flat list of every registered step name across all anchor kinds —
  // populates the "Stattdessen…" combobox typeahead. Computed pre-guard
  // so the hooks order stays stable across renders (rules-of-hooks).
  const knownSteps = useMemo(() => {
    if (!agentInfo.data) return [] as string[];
    return [
      ...new Set(Object.values(agentInfo.data.valid_steps_per_anchor).flat()),
    ].sort();
  }, [agentInfo.data]);
  // Esc collapses the inline-form back to the Verwerfen button without
  // submitting anything — the cheap escape hatch for "actually I was just
  // browsing, not overriding". Pre-guard so the effect-call order stays
  // stable; the inner body short-circuits when the form isn't open.
  useEffect(() => {
    if (verwerfenMode !== "form") return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        setVerwerfenMode("idle");
        setIntendedStep("");
        setReason("");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [verwerfenMode]);
  // Mirror Esc-collapse for the post-hoc drawer. Separate effect (instead
  // of merging into the one above) so each form's "Esc collapses ME"
  // doesn't accidentally close the other — both forms can be open at
  // the same time when consumed=false.
  useEffect(() => {
    if (postHocMode !== "form") return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        setPostHocMode("idle");
        setPostHocStep("");
        setPostHocReason("");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [postHocMode]);
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
  const isPending =
    extract.isPending ||
    formulate.isPending ||
    search.isPending ||
    stop.isPending ||
    evaluate.isPending ||
    promote.isPending ||
    decompose.isPending ||
    investigate.isPending ||
    del.isPending ||
    decide.isPending;

  const trimmedStep = intendedStep.trim();
  const trimmedReason = reason.trim();
  const isUnknownStep = trimmedStep !== "" && !knownSteps.includes(trimmedStep);
  const canSubmitCorrection = trimmedStep !== "" && trimmedReason !== "";

  const trimmedPostHocStep = postHocStep.trim();
  const trimmedPostHocReason = postHocReason.trim();
  const isPostHocUnknownStep =
    trimmedPostHocStep !== "" && !knownSteps.includes(trimmedPostHocStep);
  const canSubmitPostHoc =
    trimmedPostHocStep !== "" && trimmedPostHocReason !== "";

  function resetVerwerfenForm(): void {
    setVerwerfenMode("idle");
    setIntendedStep("");
    setReason("");
  }

  function resetPostHocForm(): void {
    setPostHocMode("idle");
    setPostHocStep("");
    setPostHocReason("");
  }

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

  async function handleSubmitCorrection(): Promise<void> {
    if (!canSubmitCorrection) return;
    try {
      await decide.mutateAsync({
        proposal_node_id: node.node_id,
        expert_correction: {
          intended_step: trimmedStep,
          intended_args: {},
          reason: trimmedReason,
        },
      });
      toastSuccess(
        isUnknownStep
          ? "Korrektur erfasst + Capability-Wunsch hinterlegt"
          : "Korrektur erfasst",
      );
      resetVerwerfenForm();
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleSubmitPostHoc(): Promise<void> {
    if (!canSubmitPostHoc) return;
    try {
      await decide.mutateAsync({
        proposal_node_id: node.node_id,
        expert_correction: {
          intended_step: trimmedPostHocStep,
          intended_args: {},
          reason: trimmedPostHocReason,
          post_hoc: true,
        },
      });
      toastSuccess(
        isPostHocUnknownStep
          ? "Korrektur (im Nachhinein) + Capability-Wunsch hinterlegt"
          : "Korrektur (im Nachhinein) erfasst",
      );
      resetPostHocForm();
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
                  className="rounded border border-chrome2-500 bg-chrome2-900/50 px-2 py-1.5"
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
      {/* Shared datalist for both correction forms (Verwerfen-morph and
       *  post-hoc drawer). Hoisted out of the form bodies so the same
       *  id doesn't appear twice in the DOM when both forms are open
       *  simultaneously (which is allowed when consumed=false). */}
      <datalist id="plan-correction-step-options">
        {knownSteps.map((s) => (
          <option key={s} value={s}>
            {STEP_LABEL[s] ?? s}
          </option>
        ))}
      </datalist>
      {/* Decision-time footer. Hidden once the plan has spawned a
       *  downstream action_proposal (consumed=true): firing Akzeptieren
       *  again would double-execute the step, and Verwerfen on a plan
       *  that already has children would orphan them. The post-hoc
       *  drawer below remains the only meaningful action in that state. */}
      {!view.consumed && (
        <footer className="p-3 border-t border-chrome2-500 space-y-2">
          <button
            type="button"
            onClick={() => void handleAccept()}
            disabled={isPending || verwerfenMode === "form"}
            className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} disabled:opacity-50`}
          >
            {isPending ? "…" : "Akzeptieren"}
          </button>
          {verwerfenMode === "idle" ? (
            <button
              type="button"
              onClick={() => setVerwerfenMode("form")}
              disabled={isPending}
              className={`w-full px-3 py-2 rounded border border-amber-700 text-amber-300 hover:bg-amber-900/30 ${T.body} disabled:opacity-50`}
            >
              Verwerfen
            </button>
          ) : (
            // Inline "Lieber so"-form. Captures (a) what the expert
            // would do instead — combobox-typeahead over known steps
            // + raw-string fallback for unimplemented methods — and
            // (b) the reason. POST /decide with the typed
            // expert_correction block (post_hoc defaults to false).
            <CorrectionFormBody
              accent="amber"
              datalistId="plan-correction-step-options"
              step={intendedStep}
              onStepChange={setIntendedStep}
              reason={reason}
              onReasonChange={setReason}
              isPending={isPending}
              isUnknownStep={isUnknownStep}
              canSubmit={canSubmitCorrection}
              onSubmit={() => void handleSubmitCorrection()}
              onCancel={resetVerwerfenForm}
              submitLabel="Korrektur erfassen"
              deleteAction={{
                label: "Doch löschen",
                onClick: () => void handleDismiss(),
              }}
            />
          )}
        </footer>
      )}
      {/* Post-hoc drawer (Phase-2). Permanent secondary footer for the
       *  "I realised too late" case — submits the same correction body
       *  but with post_hoc=true so audits can tell decision-time vs
       *  after-the-fact corrections apart. Rendered regardless of
       *  consumed; becomes the only available action once consumed. */}
      <section
        className="p-3 border-t border-chrome2-500"
        data-testid="plan-posthoc-drawer"
      >
        {postHocMode === "idle" ? (
          <button
            type="button"
            onClick={() => setPostHocMode("form")}
            disabled={isPending}
            data-testid="plan-posthoc-toggle"
            className={`w-full px-3 py-2 rounded border border-slate-600 text-slate-300 hover:bg-slate-800/40 ${T.tiny} disabled:opacity-50 text-left`}
          >
            Im Nachhinein: Korrektur erfassen…
          </button>
        ) : (
          <CorrectionFormBody
            accent="slate"
            datalistId="plan-correction-step-options"
            step={postHocStep}
            onStepChange={setPostHocStep}
            reason={postHocReason}
            onReasonChange={setPostHocReason}
            isPending={isPending}
            isUnknownStep={isPostHocUnknownStep}
            canSubmit={canSubmitPostHoc}
            onSubmit={() => void handleSubmitPostHoc()}
            onCancel={resetPostHocForm}
            submitLabel="Korrektur (im Nachhinein) erfassen"
          />
        )}
      </section>
    </div>
  );
}

interface CorrectionFormProps {
  step: string;
  onStepChange: (v: string) => void;
  reason: string;
  onReasonChange: (v: string) => void;
  isPending: boolean;
  isUnknownStep: boolean;
  canSubmit: boolean;
  onSubmit: () => void;
  onCancel: () => void;
  submitLabel: string;
  datalistId: string;
  /** Amber for decision-time (Verwerfen-morph) — same hue as the
   *  Akzeptieren CTA so the override path reads as a sibling of accept.
   *  Slate for the post-hoc drawer — calmer, reflective tone. */
  accent: "amber" | "slate";
  deleteAction?: { label: string; onClick: () => void };
}

function CorrectionFormBody({
  step,
  onStepChange,
  reason,
  onReasonChange,
  isPending,
  isUnknownStep,
  canSubmit,
  onSubmit,
  onCancel,
  submitLabel,
  datalistId,
  accent,
  deleteAction,
}: CorrectionFormProps): JSX.Element {
  const styles =
    accent === "amber"
      ? {
          wrapper: "border-amber-700/60 bg-amber-900/20",
          inputText: "text-amber-200",
          submitBtn: "bg-amber-500 hover:bg-amber-400 text-amber-950",
          hint: "text-amber-300",
        }
      : {
          wrapper: "border-slate-600/60 bg-slate-800/40",
          inputText: "text-slate-200",
          submitBtn: "bg-slate-500 hover:bg-slate-400 text-slate-950",
          hint: "text-slate-300",
        };
  return (
    <div className={`space-y-2 rounded border p-2 ${styles.wrapper}`}>
      <label className={`${T.tinyBold} block`}>
        Stattdessen…
        <input
          type="text"
          list={datalistId}
          value={step}
          onChange={(e) => onStepChange(e.target.value)}
          placeholder="extract_claims, formulate_task, … oder neue Methode"
          autoFocus
          className={`mt-1 w-full px-2 py-1.5 rounded bg-chrome2-900 border border-chrome2-500 font-mono text-sm ${styles.inputText}`}
        />
      </label>
      {isUnknownStep && (
        <p className={`${T.tiny} ${styles.hint}`}>
          Neuer Skill — wird auch als Capability-Wunsch erfasst
        </p>
      )}
      <label className={`${T.tinyBold} block`}>
        Warum?
        <textarea
          value={reason}
          onChange={(e) => onReasonChange(e.target.value)}
          rows={2}
          placeholder="Was hat der Agent übersehen?"
          required
          className="mt-1 w-full px-2 py-1.5 rounded bg-chrome2-900 border border-chrome2-500 text-slate-200 text-sm resize-none"
        />
      </label>
      <button
        type="button"
        onClick={onSubmit}
        disabled={isPending || !canSubmit}
        className={`w-full px-3 py-1.5 rounded font-semibold ${T.body} disabled:opacity-50 ${styles.submitBtn}`}
      >
        {submitLabel}
      </button>
      <div
        className={`flex items-center ${deleteAction ? "justify-between" : "justify-end"}`}
      >
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className={`${T.tiny} text-slate-400 hover:text-slate-200 underline disabled:opacity-50`}
        >
          Abbrechen
        </button>
        {deleteAction && (
          <button
            type="button"
            onClick={deleteAction.onClick}
            disabled={isPending}
            className={`${T.tiny} text-rose-400 hover:text-rose-300 underline disabled:opacity-50`}
          >
            {deleteAction.label}
          </button>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";

import { Sparkles } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useFormulateTask,
  useNextStepStream,
  useProposeStop,
  useSession,
  useSetClaimGoal,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { AnnotationCard, groupAnnotationsByKind } from "./annotations";

/**
 * Side panel for a Claim tile. Actions: formulate the search task,
 * propose stop, edit the per-claim research goal, delete (cascade).
 * The task itself is a downstream tile with its own panel — this one
 * doesn't show search/top_k controls anymore.
 */
export function ClaimPanel({
  sessionId,
  token,
  view,
  nodes,
  edges,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "claim") return <></>;
  const claim = view.claim;
  const closed = !!view.closedByStop;
  const session = useSession(sessionId, token);
  const sessionGoal = String(session.data?.meta.goal ?? "").trim();
  const sourceNodeId = String(claim.payload.source_node_id ?? "");
  const sourceChunk = sourceNodeId
    ? nodes.find((n) => n.node_id === sourceNodeId)
    : undefined;
  const sourceChunkText = sourceChunk
    ? String(sourceChunk.payload.text ?? "").trim()
    : "";
  const claimText = String(claim.payload.text ?? "");
  const depthRaw = claim.payload.recursion_depth;
  const depth = typeof depthRaw === "number" ? depthRaw : 0;
  // Don't show the chunk twice if it equals the claim (single-sentence).
  const showSourceChunk =
    sourceChunkText.length > 0 && sourceChunkText !== claimText.trim();
  // Generic enrichment-annotation pickup: every Node connected to
  // this claim via an `enriches` edge is treated as an annotation
  // produced by an `enrichment` skill. Grouped by Node `kind`,
  // newest-first per group so we can show the latest annotation.
  // (The seeded default skill emits `kind="claim_background"`;
  // future enrichment skills can use any kind, e.g.
  // `claim_translation`.)
  const annotationGroups = groupAnnotationsByKind(
    nodes,
    edges,
    claim.node_id,
  );

  const formulate = useFormulateTask(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const setClaimGoal = useSetClaimGoal(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  async function handleNextStep(): Promise<void> {
    await stream.start(claim.node_id);
  }

  const initialGoal = String(claim.payload.goal ?? "");
  const [goalDraft, setGoalDraft] = useState(initialGoal);
  const [editingGoal, setEditingGoal] = useState(false);
  useEffect(() => {
    if (!editingGoal) setGoalDraft(initialGoal);
  }, [initialGoal, editingGoal]);

  async function handleFormulate(): Promise<void> {
    try {
      await formulate.mutateAsync({ claim_node_id: claim.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleStop(): Promise<void> {
    try {
      await stop.mutateAsync({ anchor_node_id: claim.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (
      !window.confirm(
        "Aussage und alle abhängigen Knoten (Aufgabe, Treffer, Bewertungen) löschen?",
      )
    ) {
      return;
    }
    try {
      await del.mutateAsync(claim.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleSaveGoal(): Promise<void> {
    if (!goalDraft.trim() || goalDraft.trim() === initialGoal) {
      setEditingGoal(false);
      return;
    }
    try {
      await setClaimGoal.mutateAsync({
        claimId: claim.node_id,
        goal: goalDraft.trim(),
      });
      setEditingGoal(false);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader title="Aussage" onClose={() => onSelectView(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        {sessionGoal && (
          <div className="rounded border border-amber-700/40 bg-amber-950/20 px-3 py-2">
            <p className={`${T.tinyBold} text-amber-300`}>Sitzungs-Ziel</p>
            <p className={`text-amber-100 ${T.body} mt-0.5`}>{sessionGoal}</p>
          </div>
        )}
        <div>
          <p className={T.tinyBold}>Text</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
            {claimText}
          </p>
          {depth > 0 && (
            <p
              className={`${T.mono} ${T.tiny} text-cyan-300 mt-1`}
              title={`Aus einem ${depth}× abgeleiteten Chunk extrahiert.`}
            >
              ↳ Ebene {depth}
            </p>
          )}
        </div>
        {annotationGroups.map((group) => (
          <AnnotationCard key={group.kind} group={group} />
        ))}
        {showSourceChunk && (
          <details
            className="rounded border border-navy-700 bg-navy-900/40"
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-slate-300`}
            >
              Quell-Textabschnitt{" "}
              <span className="font-normal text-slate-500">
                ({sourceChunkText.length} Zeichen)
              </span>
            </summary>
            <p
              className={`px-3 pb-3 pt-1 text-slate-300 ${T.tiny} whitespace-pre-wrap italic`}
            >
              {sourceChunkText.length > 1500
                ? sourceChunkText.slice(0, 1500) + " […]"
                : sourceChunkText}
            </p>
            <button
              type="button"
              onClick={() => onSelectView(`view:${sourceNodeId}`)}
              className={`mx-3 mb-3 px-2 py-1 rounded bg-navy-800 hover:bg-navy-700 text-slate-300 ${T.tiny}`}
            >
              Chunk-Tile öffnen →
            </button>
          </details>
        )}
        <div className="pt-2 border-t border-navy-700">
          <p className={`${T.tinyBold} text-pink-300`}>
            Recherche-Frage zu dieser Aussage
          </p>
          {editingGoal ? (
            <div className="mt-1 space-y-1">
              <textarea
                value={goalDraft}
                onChange={(e) => setGoalDraft(e.target.value)}
                rows={3}
                className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
                placeholder="z.B. Wo steht im Korpus, dass die Wärmeleistung 5.6 kW beträgt?"
                autoFocus
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleSaveGoal()}
                  disabled={setClaimGoal.isPending || !goalDraft.trim()}
                  className={`px-2 py-1 rounded bg-pink-600 hover:bg-pink-500 text-white ${T.tiny} disabled:opacity-50`}
                >
                  {setClaimGoal.isPending ? "…" : "Speichern"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setGoalDraft(initialGoal);
                    setEditingGoal(false);
                  }}
                  className={`px-2 py-1 rounded text-slate-300 hover:bg-navy-700 ${T.tiny}`}
                >
                  Abbrechen
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setEditingGoal(true)}
              className={`mt-1 text-left w-full ${T.body} ${
                initialGoal ? "text-pink-100 italic" : "text-slate-500 italic"
              } hover:text-pink-200`}
              title="Klick zum Bearbeiten"
            >
              {initialGoal || "(noch nicht gesetzt — klick zum Setzen)"}
            </button>
          )}
        </div>
        {closed && (
          <p className={`${T.body} text-amber-300 italic`}>
            Diese Untersuchung wurde abgeschlossen.
          </p>
        )}
        <LiveRunPanel
          run={stream}
          anchorPreview={String(claim.payload.text ?? "").slice(0, 120)}
          goal={initialGoal || undefined}
          onClose={() => stream.reset()}
        />
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleNextStep()}
          disabled={stream.isRunning}
          className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
        >
          <Sparkles className="w-4 h-4" aria-hidden />
          {stream.isRunning ? "Agent denkt…" : "Was als nächstes?"}
        </button>
        <details className="rounded border border-navy-700 bg-navy-900/40">
          <summary className={`${T.tiny} cursor-pointer px-2 py-1 text-slate-400`}>
            Manuell wählen
          </summary>
          <div className="p-2 space-y-2">
            <button
              type="button"
              onClick={() => void handleFormulate()}
              disabled={formulate.isPending}
              className={`w-full px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white ${T.tiny} disabled:opacity-50`}
            >
              {formulate.isPending ? "…" : "Aufgabe formulieren"}
            </button>
            <button
              type="button"
              onClick={() => void handleStop()}
              disabled={stop.isPending}
              className={`w-full px-3 py-1.5 rounded bg-zinc-600 hover:bg-zinc-500 text-white ${T.tiny} disabled:opacity-50`}
            >
              {stop.isPending ? "…" : "Stopp vorschlagen"}
            </button>
          </div>
        </details>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Tile löschen"}
        </button>
        {(formulate.error || stop.error || del.error) && (
          <p className={`text-red-400 ${T.tiny}`}>
            {(formulate.error ?? stop.error ?? del.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}


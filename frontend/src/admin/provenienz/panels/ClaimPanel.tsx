import { useEffect, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useFormulateTask,
  useProposeStop,
  useSetClaimGoal,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

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
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "claim") return <></>;
  const claim = view.claim;
  const closed = !!view.closedByStop;

  const formulate = useFormulateTask(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const setClaimGoal = useSetClaimGoal(token, sessionId);
  const { error: toastError } = useToast();

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
        <div>
          <p className={T.tinyBold}>Text</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
            {String(claim.payload.text ?? "")}
          </p>
        </div>
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
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleFormulate()}
          disabled={formulate.isPending}
          className={`w-full px-3 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white ${T.body} disabled:opacity-50`}
        >
          {formulate.isPending ? "…" : "Aufgabe formulieren"}
        </button>
        <button
          type="button"
          onClick={() => void handleStop()}
          disabled={stop.isPending}
          className={`w-full px-3 py-2 rounded bg-zinc-600 hover:bg-zinc-500 text-white ${T.body} disabled:opacity-50`}
        >
          {stop.isPending ? "…" : "Stopp vorschlagen"}
        </button>
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

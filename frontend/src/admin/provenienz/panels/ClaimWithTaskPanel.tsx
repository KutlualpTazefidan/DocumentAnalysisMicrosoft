import { useEffect, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useFormulateTask,
  useProposeStop,
  useSearchStep,
  useSetClaimGoal,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

/**
 * Combined panel for the claim+task tile. Shows the claim text + (if any) the
 * formulated task query. Action buttons depend on state:
 *   - no task yet → "Aufgabe formulieren" + "Stopp vorschlagen"
 *   - task exists, no search yet → "Suchen" + "Stopp vorschlagen"
 *   - task already searched → search bag tile carries the next actions
 */
export function ClaimWithTaskPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "claim_with_task") return <></>;
  const claim = view.claim;
  const task = view.task;
  const closed = !!view.closedByStop;

  const formulate = useFormulateTask(token, sessionId);
  const search = useSearchStep(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const setClaimGoal = useSetClaimGoal(token, sessionId);
  const { error: toastError } = useToast();
  const [topK, setTopK] = useState(5);
  const initialGoal = String(claim.payload.goal ?? "");
  const [goalDraft, setGoalDraft] = useState(initialGoal);
  const [editingGoal, setEditingGoal] = useState(false);
  useEffect(() => {
    if (!editingGoal) setGoalDraft(initialGoal);
  }, [initialGoal, editingGoal]);

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

  async function handleFormulate(): Promise<void> {
    try {
      await formulate.mutateAsync({ claim_node_id: claim.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleSearch(): Promise<void> {
    if (!task) return;
    try {
      await search.mutateAsync({ task_node_id: task.node_id, top_k: topK });
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
        "Aussage und alle abhängigen Knoten (Suchanfrage, Treffer, " +
          "Bewertungen, abgeleitete Chunks) löschen? Die Einträge bleiben " +
          "im Audit-Log, werden aber im Canvas ausgeblendet.",
      )
    ) {
      return;
    }
    try {
      // Backend cascades automatically — single call removes the whole subtree.
      await del.mutateAsync(claim.node_id);
      onSelectView(null);
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
                initialGoal
                  ? "text-pink-100 italic"
                  : "text-slate-500 italic"
              } hover:text-pink-200`}
              title="Klick zum Bearbeiten"
            >
              {initialGoal || "(noch nicht gesetzt — klick zum Setzen)"}
            </button>
          )}
        </div>
        {task && (
          <div className="pt-2 border-t border-navy-700">
            <p className={T.tinyBold}>Suchanfrage</p>
            <p className={`text-cyan-200 italic ${T.body}`}>
              {String(task.payload.query ?? "")}
            </p>
          </div>
        )}
        {closed && (
          <p className={`${T.body} text-amber-300 italic`}>
            Diese Untersuchung wurde abgeschlossen.
          </p>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        {!task && (
          <button
            type="button"
            onClick={() => void handleFormulate()}
            disabled={formulate.isPending}
            className={`w-full px-3 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white ${T.body} disabled:opacity-50`}
          >
            {formulate.isPending ? "…" : "Aufgabe formulieren"}
          </button>
        )}
        {task && (
          <>
            <div className="flex items-center gap-2">
              <label className={`${T.tiny} text-slate-300`}>top_k</label>
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Math.max(1, Math.min(20, Number(e.target.value))))}
                className={`w-16 px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSearch()}
              disabled={search.isPending}
              className={`w-full px-3 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white ${T.body} disabled:opacity-50`}
            >
              {search.isPending ? "Suche…" : "Suchen"}
            </button>
          </>
        )}
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
        {(formulate.error || search.error || stop.error || del.error) && (
          <p className={`text-red-400 ${T.tiny}`}>
            {(formulate.error ?? search.error ?? stop.error ?? del.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}

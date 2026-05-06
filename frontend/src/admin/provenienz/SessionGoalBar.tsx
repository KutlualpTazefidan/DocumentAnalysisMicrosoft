import { useEffect, useState } from "react";
import { Pencil, Target } from "lucide-react";

import { useToast } from "../../shared/components/useToast";
import { useSetGoal } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  sessionId: string;
  token: string;
  goal: string;
}

/**
 * Inline editor for the session goal. Auto-derived from the chunk + first
 * claim by ``extract_goal`` after the first /decide acceptance; until then
 * a hint reads "noch nicht gesetzt — wird nach erster Aussage erzeugt."
 * Manually editable at any time.
 */
export function SessionGoalBar({ sessionId, token, goal }: Props): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(goal);
  const setGoal = useSetGoal(token, sessionId);
  const { error: toastError } = useToast();

  // Keep the draft in sync when the prop changes (e.g. auto-extract landed).
  useEffect(() => {
    if (!editing) setDraft(goal);
  }, [goal, editing]);

  async function handleSave(): Promise<void> {
    if (!draft.trim()) return;
    try {
      await setGoal.mutateAsync(draft.trim());
      setEditing(false);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  if (editing) {
    return (
      <div className="rounded border border-blue-700 bg-blue-900/30 px-3 py-1.5 flex items-center gap-2">
        <Target className="w-4 h-4 text-blue-300 shrink-0" aria-hidden />
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSave();
            if (e.key === "Escape") {
              setDraft(goal);
              setEditing(false);
            }
          }}
          className={`flex-1 bg-navy-900 border border-navy-600 rounded px-2 py-0.5 text-white ${T.body}`}
          autoFocus
          placeholder="Recherche-Ziel als Frage formulieren…"
        />
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={setGoal.isPending || !draft.trim()}
          className={`px-2 py-0.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.tiny} disabled:opacity-50`}
        >
          {setGoal.isPending ? "…" : "Speichern"}
        </button>
        <button
          type="button"
          onClick={() => {
            setDraft(goal);
            setEditing(false);
          }}
          className={`px-2 py-0.5 rounded text-slate-300 hover:bg-navy-700 ${T.tiny}`}
        >
          Abbrechen
        </button>
      </div>
    );
  }

  const empty = !goal.trim();
  return (
    <div className="rounded border border-navy-700 bg-navy-800/40 px-3 py-1.5 flex items-center gap-2 group">
      <Target
        className={`w-4 h-4 shrink-0 ${empty ? "text-slate-500" : "text-blue-300"}`}
        aria-hidden
      />
      <div className="flex-1 min-w-0">
        <p className={`${T.tiny} text-slate-400 leading-tight`}>Recherche-Ziel</p>
        {empty ? (
          <p className={`${T.body} text-slate-500 italic truncate`}>
            noch nicht gesetzt — wird nach erster Aussage automatisch abgeleitet
          </p>
        ) : (
          <p className={`${T.body} text-white truncate`}>{goal}</p>
        )}
      </div>
      <button
        type="button"
        onClick={() => setEditing(true)}
        className={`p-1 rounded text-slate-400 hover:text-white hover:bg-navy-700 opacity-0 group-hover:opacity-100 transition-opacity`}
        aria-label="Ziel bearbeiten"
        title="Ziel bearbeiten"
      >
        <Pencil className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

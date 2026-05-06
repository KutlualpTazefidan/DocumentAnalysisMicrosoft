import { useEffect, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import { useSetGoal } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function GoalPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  // Hooks must run unconditionally — read text via narrowing-friendly access.
  const initial = view.kind === "goal" ? view.text : "";
  const [draft, setDraft] = useState(initial);
  const setGoal = useSetGoal(token, sessionId);
  const { error: toastError } = useToast();

  useEffect(() => {
    if (view.kind === "goal") setDraft(view.text);
  }, [view]);

  if (view.kind !== "goal") return <></>;

  async function handleSave(): Promise<void> {
    if (view.kind !== "goal") return;
    if (!draft.trim() || draft.trim() === view.text) return;
    try {
      await setGoal.mutateAsync(draft.trim());
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  const empty = !view.text.trim();
  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Recherche-Ziel"
        subtitle={empty ? "noch nicht gesetzt" : "wird vom Planer gelesen"}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Ziel als Frage formulieren</p>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            placeholder="z.B. Welche Quelle belegt die Wärmeleistung von 5.6 kW?"
            className={`mt-1 w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
            autoFocus={empty}
          />
          <p className={`${T.tiny} text-slate-500 mt-1`}>
            Auto-extrahiert nach erster Aussage. Manuell überschreibbar; der
            Planer nutzt diesen Text als oberste Eingabe.
          </p>
        </div>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={
            setGoal.isPending || !draft.trim() || draft.trim() === view.text
          }
          className={`w-full px-3 py-2 rounded bg-pink-600 hover:bg-pink-500 text-white ${T.body} disabled:opacity-50`}
        >
          {setGoal.isPending ? "Speichere…" : "Ziel speichern"}
        </button>
        {setGoal.error && (
          <p className={`text-red-400 ${T.tiny}`}>{setGoal.error.message}</p>
        )}
      </footer>
    </div>
  );
}

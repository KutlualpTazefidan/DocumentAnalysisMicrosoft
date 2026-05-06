import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function ManualReviewPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "manual_review") return <></>;
  const node = view.review;
  const p = node.payload as {
    name?: string;
    description?: string;
    reasoning?: string;
    confidence?: number;
  };
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();

  async function handleDismiss(): Promise<void> {
    if (!window.confirm("Mensch-Aufgabe als erledigt verwerfen?")) return;
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
        title="Mensch-Aufgabe"
        subtitle={p.name || "—"}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {p.description && (
          <div>
            <p className={T.tinyBold}>Was zu tun ist</p>
            <p className={`text-rose-100 ${T.body} whitespace-pre-wrap`}>
              {p.description}
            </p>
          </div>
        )}
        {p.reasoning && (
          <div>
            <p className={T.tinyBold}>Warum Mensch-only</p>
            <p className={`text-slate-200 ${T.body} italic whitespace-pre-wrap`}>
              {p.reasoning}
            </p>
          </div>
        )}
        <p className={`${T.tiny} text-slate-500 italic`}>
          Der Agent hat eskaliert. Erledige die Aufgabe manuell und
          markiere sie unten als erledigt.
        </p>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleDismiss()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-rose-700 text-rose-300 hover:bg-rose-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Als erledigt markieren"}
        </button>
      </footer>
    </div>
  );
}

import { useToast } from "../../../shared/components/useToast";
import { useExtractClaims } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function ChunkPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "chunk") return <></>;
  const chunk = view.chunk;
  const text = String(chunk.payload.text ?? "");
  const boxId = chunk.payload.box_id ? String(chunk.payload.box_id) : null;
  const closed = !!view.closedByStop;

  const extract = useExtractClaims(token, sessionId);
  const { error: toastError } = useToast();

  async function handleExtract(): Promise<void> {
    try {
      await extract.mutateAsync({ chunk_node_id: chunk.node_id });
      // The new pending_proposal view tile takes over; auto-select it.
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Chunk"
        subtitle={boxId ?? undefined}
        onClose={() => onSelectView(null)}
      />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Text</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
            {text}
          </p>
        </div>
        {closed && (
          <p className={`${T.body} text-amber-300 italic`}>
            Diese Chunk-Untersuchung wurde abgeschlossen.
          </p>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleExtract()}
          disabled={extract.isPending}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {extract.isPending ? "Extrahiere…" : "Aussagen extrahieren"}
        </button>
        {extract.error && (
          <p className={`text-red-400 ${T.tiny}`}>{extract.error.message}</p>
        )}
      </footer>
    </div>
  );
}

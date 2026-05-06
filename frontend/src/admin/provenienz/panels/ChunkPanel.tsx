import { CornerDownRight } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useExtractClaims,
  type ProvNode,
} from "../../hooks/useProvenienz";
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
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();

  async function handleExtract(): Promise<void> {
    try {
      await extract.mutateAsync({ chunk_node_id: chunk.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleDelete(): Promise<void> {
    const isPromoted = view.kind === "chunk" && view.promoted;
    const message = isPromoted
      ? "Diesen abgeleiteten Chunk und alle abhängigen Aussagen + Suchen löschen?"
      : "Diesen Chunk und seinen gesamten Untersuchungsbaum löschen? " +
        "(Aussagen, Suchanfragen, Treffer, Bewertungen werden ausgeblendet — " +
        "bleiben aber im Audit-Log.)";
    if (!window.confirm(message)) return;
    try {
      await del.mutateAsync(chunk.node_id);
      onSelectView(null);
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
        <OriginContext chunk={chunk} />
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
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Tile löschen"}
        </button>
        {(extract.error || del.error) && (
          <p className={`text-red-400 ${T.tiny}`}>
            {(extract.error ?? del.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}

/**
 * Breadcrumb block shown when a chunk was created via "Weiter erforschen"
 * on a search result. Surfaces the original claim + query + source chunk
 * box_id so the user remembers the recursive trail. The same data is
 * stitched into the next ``extract_claims`` LLM call's system prompt
 * server-side so the LLM stays on-topic for the recursive exploration.
 */
function OriginContext({ chunk }: { chunk: ProvNode }): JSX.Element | null {
  const p = chunk.payload;
  if (!p.promoted_from) return null;
  const claimText = typeof p.origin_claim_text === "string" ? p.origin_claim_text : "";
  const query = typeof p.origin_query === "string" ? p.origin_query : "";
  const originBox = typeof p.origin_chunk_box_id === "string" ? p.origin_chunk_box_id : "";
  return (
    <section className="rounded border border-purple-700/50 bg-purple-900/20 px-3 py-2">
      <p className={`${T.tinyBold} text-purple-300 flex items-center gap-1`}>
        <CornerDownRight className="w-3 h-3" aria-hidden /> Recherche-Kontext
      </p>
      {claimText && (
        <div className="mt-1.5">
          <p className={`${T.tiny} text-purple-300`}>Ursprüngliche Aussage</p>
          <p className={`${T.body} text-purple-100 italic`}>„{claimText}"</p>
        </div>
      )}
      {query && (
        <div className="mt-1.5">
          <p className={`${T.tiny} text-purple-300`}>Suchanfrage</p>
          <p className={`${T.body} text-purple-100`}>„{query}"</p>
        </div>
      )}
      {originBox && (
        <div className="mt-1.5">
          <p className={`${T.tiny} text-purple-300`}>Ursprünglicher Chunk</p>
          <p className={`${T.mono} text-purple-100`}>{originBox}</p>
        </div>
      )}
      <p className={`${T.tiny} text-purple-300/70 italic mt-2`}>
        Wird beim Extrahieren als Kontext an den LLM übergeben.
      </p>
    </section>
  );
}

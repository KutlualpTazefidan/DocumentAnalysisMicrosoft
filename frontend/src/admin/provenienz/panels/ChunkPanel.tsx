import { CornerDownRight, RefreshCw, Sparkles } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useExtractClaims,
  useNextStepStream,
  useRefreshChunk,
  type ProvNode,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
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
  const stream = useNextStepStream(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const refresh = useRefreshChunk(token, sessionId);
  const { error: toastError, info: toastInfo, success: toastSuccess } = useToast();

  async function handleNextStep(): Promise<void> {
    await stream.start(chunk.node_id);
  }

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

  async function handleRefresh(): Promise<void> {
    try {
      const out = await refresh.mutateAsync(chunk.node_id);
      if (!out.refreshed) {
        if (out.reason === "source-missing") {
          toastError(
            "Quelle nicht gefunden — die Box wurde im Extract-Tab gelöscht.",
          );
        } else {
          toastInfo("Quelle bereits aktuell — kein neuer Chunk nötig.");
        }
        return;
      }
      toastSuccess("Neuer Chunk aus aktueller Quelle erstellt.");
      if (out.new_chunk) {
        // ViewNode ids are minted as `view:<node_id>` in layout.ts. The
        // session-detail query was just invalidated by useRefreshChunk;
        // by the time the canvas re-renders the new view-node will be in
        // the index and SidePanel resolves the selection.
        onSelectView(`view:${out.new_chunk.node_id}`);
      }
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
        {typeof chunk.payload.caption_text === "string" &&
          chunk.payload.caption_text && (
            <div className="rounded border border-cyan-700/40 bg-cyan-950/20 px-3 py-2">
              <p className={`${T.tinyBold} text-cyan-300`}>
                📑 Caption ({String(chunk.payload.caption_box_id ?? "")})
              </p>
              <p className={`text-cyan-100 ${T.body} mt-0.5`}>
                {String(chunk.payload.caption_text)}
              </p>
            </div>
          )}
        <div className="flex items-center justify-between gap-2">
          <BoxMetadataStrip chunk={chunk} />
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refresh.isPending}
            title="Mit aktueller segments.json abgleichen. Bei Abweichung entsteht ein neuer Chunk; der alte bleibt für den Audit."
            className={`shrink-0 px-2 py-1 rounded border border-orange-700/60 text-orange-300 hover:bg-orange-900/30 ${T.tiny} flex items-center gap-1 disabled:opacity-50`}
          >
            <RefreshCw
              className={`w-3 h-3 ${refresh.isPending ? "animate-spin" : ""}`}
              aria-hidden
            />
            {refresh.isPending ? "Prüfe…" : "Quelle aktualisieren"}
          </button>
        </div>
        {closed && (
          <p className={`${T.body} text-amber-300 italic`}>
            Diese Chunk-Untersuchung wurde abgeschlossen.
          </p>
        )}
        <LiveRunPanel
          run={stream}
          anchorPreview={text.slice(0, 120)}
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
              onClick={() => void handleExtract()}
              disabled={extract.isPending}
              className={`w-full px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.tiny} disabled:opacity-50`}
            >
              {extract.isPending ? "…" : "Aussagen extrahieren"}
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
        {(extract.error || del.error || refresh.error) && (
          <p className={`text-red-400 ${T.tiny}`}>
            {(extract.error ?? del.error ?? refresh.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}

/**
 * Compact strip of structured box metadata copied from segments.json onto
 * the chunk payload at session-creation time. Hides any field that is
 * null/missing — pre-Phase-A sessions only carry box_id/doc_slug/text and
 * therefore render nothing here.
 */
function BoxMetadataStrip({ chunk }: { chunk: ProvNode }): JSX.Element | null {
  const p = chunk.payload;
  const page = typeof p.page === "number" ? p.page : null;
  const boxKind =
    typeof p.box_kind === "string" && p.box_kind ? p.box_kind : null;
  const readingOrder =
    typeof p.reading_order === "number" ? p.reading_order : null;
  const bbox = Array.isArray(p.bbox) && p.bbox.length === 4 ? p.bbox : null;
  const confidence = typeof p.confidence === "number" ? p.confidence : null;
  const depth = typeof p.recursion_depth === "number" ? p.recursion_depth : 0;

  const parts: string[] = [];
  if (page !== null) parts.push(`Seite ${page}`);
  if (readingOrder !== null) parts.push(`#${readingOrder}`);
  if (boxKind) parts.push(boxKind);
  if (bbox) {
    const w = Math.round(Number(bbox[2]) - Number(bbox[0]));
    const h = Math.round(Number(bbox[3]) - Number(bbox[1]));
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
      parts.push(`${w}×${h} px`);
    }
  }
  if (depth > 0) parts.push(`↳ Ebene ${depth}`);

  if (parts.length === 0) return null;

  const title =
    confidence !== null ? `Konfidenz ${confidence.toFixed(2)}` : undefined;

  return (
    <p
      className={`${T.mono} ${T.tiny} text-slate-400`}
      title={title}
    >
      {parts.join(" · ")}
    </p>
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

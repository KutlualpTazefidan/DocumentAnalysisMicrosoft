import { CornerDownRight, FolderOpen, Sparkles, Trash2 } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useCrossDocSearchStep,
  useDeleteNode,
  useEvaluate,
  useNextStepStream,
  usePromoteSearchResult,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { AnnotationCard, groupAnnotationsByKind } from "./annotations";

interface CorpusMatch {
  slug: string;
  filename: string;
  score: number;
  matched_tokens: string[];
}

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-700 text-emerald-100",
  "partial-support": "bg-amber-600 text-amber-50",
  unrelated: "bg-slate-600 text-slate-200",
  contradicts: "bg-rose-700 text-rose-100",
  manual: "bg-purple-600 text-purple-100",
};

/**
 * Detail panel for a search_result tile that's been extracted from
 * the bag (because it has downstream agent-flow). Same controls as
 * the per-row block in SearchResultsBagPanel — primary
 * "Was als nächstes?" button + manual-fallback accordion.
 */
export function SearchResultPanel({
  sessionId,
  token,
  view,
  nodes,
  edges,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "search_result") return <></>;
  const result = view.result;
  const evalNode = view.evaluation;
  // Forward-compat: enrichment skills with `output.attaches_to ==
  // "search_result"` will surface here automatically once any are
  // configured. Today no such skills exist, so this renders nothing.
  const annotationGroups = groupAnnotationsByKind(
    nodes,
    edges,
    result.node_id,
  );
  const p = result.payload as {
    box_id?: string;
    score?: number;
    text?: string;
    page?: number;
    box_kind?: string;
    reading_order?: number;
    bbox?: number[];
    caption_box_id?: string;
    caption_text?: string;
    /** Set by the BibFileMatcher reactive hook on register-lookup
     * results with kind=bibliography when the cited document is
     * already in the local corpus. */
    corpus_match?: CorpusMatch;
    /** Identifies a register-lookup result vs. a regular BM25 hit. */
    searcher?: string;
  };
  const verdict = evalNode
    ? String((evalNode.payload as { verdict?: string }).verdict ?? "")
    : null;
  const reasoning = evalNode
    ? String((evalNode.payload as { reasoning?: string }).reasoning ?? "")
    : null;
  const confidence = evalNode
    ? Number((evalNode.payload as { confidence?: number }).confidence ?? 0)
    : null;

  const evaluate = useEvaluate(token, sessionId);
  const promote = usePromoteSearchResult(token, sessionId);
  const crossDocSearch = useCrossDocSearchStep(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  // Find the parent task Node by walking edges backward — needed to
  // continue the original task (its query) against the foreign slug
  // when the user clicks "weiterführen".
  const parentTaskId = (() => {
    const incoming = edges.filter((e) => e.to_node === result.node_id);
    for (const e of incoming) {
      const src = nodes.find((n) => n.node_id === e.from_node);
      if (src && src.kind === "task") return src.node_id;
    }
    return null;
  })();

  async function handleEvaluate(): Promise<void> {
    try {
      await evaluate.mutateAsync({ search_result_node_id: result.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handlePromote(): Promise<void> {
    try {
      const newChunk = await promote.mutateAsync(result.node_id);
      onSelectView(`view:${newChunk.node_id}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (!window.confirm("Treffer + abhängige Bewertung/Chunks löschen?")) return;
    try {
      await del.mutateAsync(result.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleContinueInCorpusMatch(): Promise<void> {
    if (!parentTaskId || !p.corpus_match) return;
    try {
      await crossDocSearch.mutateAsync({
        task_node_id: parentTaskId,
        target_slug: p.corpus_match.slug,
        triggered_from_node_id: result.node_id,
      });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Suchtreffer"
        subtitle={String(p.box_id ?? "")}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className={`flex items-center gap-2 flex-wrap ${T.tiny}`}>
          <span className="text-slate-400">
            Score {Number(p.score ?? 0).toFixed(2)}
          </span>
          {typeof p.page === "number" && (
            <span className="text-slate-500 font-mono">
              Seite {p.page}
              {typeof p.reading_order === "number" ? ` · #${p.reading_order}` : ""}
            </span>
          )}
          {p.box_kind && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${
                p.box_kind === "table"
                  ? "bg-purple-700/50 text-purple-100 border border-purple-600/50"
                  : p.box_kind === "figure"
                    ? "bg-amber-700/50 text-amber-100 border border-amber-600/50"
                    : p.box_kind === "caption"
                      ? "bg-cyan-700/50 text-cyan-100 border border-cyan-600/50"
                      : p.box_kind === "formula"
                        ? "bg-emerald-700/50 text-emerald-100 border border-emerald-600/50"
                        : p.box_kind === "toc"
                          ? "bg-indigo-700/50 text-indigo-100 border border-indigo-600/50"
                          : p.box_kind === "list_of_tables"
                            ? "bg-purple-800/50 text-purple-100 border border-purple-700/50"
                            : p.box_kind === "list_of_figures"
                              ? "bg-amber-800/50 text-amber-100 border border-amber-700/50"
                              : p.box_kind === "bibliography"
                                ? "bg-emerald-800/50 text-emerald-100 border border-emerald-700/50"
                                : "bg-navy-700 text-slate-300 border border-navy-600"
              }`}
              title={`Box-Typ: ${p.box_kind}`}
            >
              {p.box_kind}
            </span>
          )}
          {verdict && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${
                VERDICT_STYLE[verdict] ?? "bg-slate-600 text-slate-200"
              }`}
            >
              {verdict}
              {confidence !== null && ` · ${confidence.toFixed(2)}`}
            </span>
          )}
        </div>
        <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
          {String(p.text ?? "")}
        </p>
        {p.caption_text && (
          <div className="rounded border border-cyan-700/40 bg-cyan-950/20 px-3 py-2">
            <p className={`${T.tinyBold} text-cyan-300`}>
              📑 Caption ({p.caption_box_id})
            </p>
            <p className={`text-cyan-100 ${T.body} mt-0.5`}>{p.caption_text}</p>
          </div>
        )}
        {p.corpus_match && (
          <div className="rounded border border-emerald-700/40 bg-emerald-950/20 px-3 py-2 space-y-1">
            <p className={`${T.tinyBold} text-emerald-300`}>
              📁 Im Korpus gefunden
            </p>
            <p className={`text-emerald-100 ${T.body}`}>
              Diese Quelle entspricht <span className="font-mono">{p.corpus_match.filename}</span>
            </p>
            <p className={`${T.tiny} text-emerald-400/70`}>
              Match-Score {p.corpus_match.score} · Token-Treffer:{" "}
              <span className="font-mono">{p.corpus_match.matched_tokens.join(", ")}</span>
            </p>
            <button
              type="button"
              onClick={() => void handleContinueInCorpusMatch()}
              disabled={!parentTaskId || crossDocSearch.isPending}
              title={
                parentTaskId
                  ? `Original-Aufgabe gegen ${p.corpus_match.slug} suchen — die Treffer landen in dieser Session.`
                  : "Kein Eltern-Task gefunden — kann die Aufgabe nicht übertragen."
              }
              className={`inline-flex items-center gap-1 mt-1 px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white ${T.tiny}`}
            >
              <FolderOpen className="w-3 h-3" aria-hidden />
              {crossDocSearch.isPending
                ? "Suche…"
                : `→ Aufgabe in ${p.corpus_match.slug} weiterführen`}
            </button>
          </div>
        )}
        {annotationGroups.map((group) => (
          <AnnotationCard key={group.kind} group={group} />
        ))}
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Bewertungs-Begründung</p>
            <p className={`text-slate-300 ${T.body} italic mt-1`}>
              „{reasoning}"
            </p>
          </div>
        )}
        <LiveRunPanel run={stream} onClose={() => stream.reset()} />
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void stream.start(result.node_id)}
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
          <div className="p-2 flex gap-2">
            {!evalNode && (
              <button
                type="button"
                onClick={() => void handleEvaluate()}
                disabled={evaluate.isPending}
                className={`flex-1 px-2 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white ${T.tiny} disabled:opacity-50`}
              >
                {evaluate.isPending ? "…" : "Bewerten"}
              </button>
            )}
            <button
              type="button"
              onClick={() => void handlePromote()}
              disabled={promote.isPending}
              className={`flex-1 px-2 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white ${T.tiny} disabled:opacity-50 flex items-center justify-center gap-1`}
              title="Diesen Treffer als neuen Chunk öffnen"
            >
              <CornerDownRight className="w-3 h-3" aria-hidden />
              {promote.isPending ? "…" : "Weiter erforschen"}
            </button>
          </div>
        </details>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} disabled:opacity-50 flex items-center justify-center gap-2`}
        >
          <Trash2 className="w-3.5 h-3.5" />
          {del.isPending ? "…" : "Tile löschen"}
        </button>
      </footer>
    </div>
  );
}

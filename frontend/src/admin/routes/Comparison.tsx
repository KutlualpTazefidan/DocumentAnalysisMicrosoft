import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { DocStepTabs } from "../components/DocStepTabs";
import { getDoc } from "../api/docs";
import { useQuestions, type Question } from "../hooks/useSynthesise";
import {
  useAskPipeline,
  useCompareAnswers,
  usePipelines,
  useSimilarQuestions,
  type AskResponse,
  type SimilarHit,
} from "../hooks/useComparison";
import {
  loadApprovedPages,
  loadCurrentPage,
  saveApprovedPages,
  saveCurrentPage,
} from "../lib/currentPage";
import { T } from "../styles/typography";

/**
 * Vergleich tab — same chrome as Extract / Synthesise:
 *
 *   Left pane     : questions on this page + similar-question block
 *   Middle pane   : pipeline runner (send → chunks + answer → compare)
 *   Right strip   : page navigation widget + lock-page button
 *                   (same components Synthesise uses)
 */

function comparePageBtnClasses(hasQuestions: boolean, isActive: boolean): string {
  const base = `w-10 h-10 rounded ${T.body} font-medium flex items-center justify-center`;
  const ring = isActive ? " ring-2 ring-blue-500" : "";
  return hasQuestions
    ? `${base} bg-green-100 hover:bg-green-200 text-green-800${ring}`
    : `${base} bg-red-100 hover:bg-red-200 text-red-800${ring}`;
}

interface InnerProps {
  slug: string;
  token: string;
}

function ComparisonInner({ slug, token }: InnerProps): JSX.Element {
  const { success, error } = useToast();
  const [page, setPage] = useState<number>(() => loadCurrentPage(slug));
  const [pageGridOpen, setPageGridOpen] = useState(false);
  const [approvedPages, setApprovedPages] = useState<Set<number>>(() =>
    loadApprovedPages(slug),
  );
  const [selectedEntry, setSelectedEntry] = useState<string | null>(null);
  const [pipelineName, setPipelineName] = useState<string>("microsoft");
  const [pipelineResult, setPipelineResult] = useState<AskResponse | null>(null);
  const [compareResult, setCompareResult] = useState<{
    bm25: number;
    cosine: number;
    embedder: boolean;
  } | null>(null);

  const docMeta = useQuery({
    queryKey: ["doc", slug],
    queryFn: () => getDoc(slug, token),
    enabled: !!slug,
  });
  const questions = useQuestions(slug, token);
  const similar = useSimilarQuestions(slug, token, selectedEntry);
  const pipelines = usePipelines(token);
  const ask = useAskPipeline(token);
  const compare = useCompareAnswers(token);

  useEffect(() => {
    saveCurrentPage(slug, page);
  }, [slug, page]);

  // Same DocMeta-first total-pages calc as Extract / Synthesise.
  const totalPages = docMeta.data?.pages ?? 1;

  // Pages-with-questions for the page-grid colouring.
  const pagesWithQuestions = useMemo<Set<number>>(() => {
    const out = new Set<number>();
    for (const [boxId, qs] of Object.entries(questions.data ?? {})) {
      if (!qs || qs.length === 0) continue;
      const m = boxId.match(/^p(\d+)-/);
      if (m) out.add(parseInt(m[1], 10));
    }
    return out;
  }, [questions.data]);

  function handleToggleApprove() {
    const next = new Set(approvedPages);
    if (next.has(page)) next.delete(page);
    else next.add(page);
    setApprovedPages(next);
    saveApprovedPages(slug, next);
  }

  // Flatten questions for the current page only.
  const questionsOnPage: Question[] = useMemo(() => {
    const out: Question[] = [];
    for (const [boxId, qs] of Object.entries(questions.data ?? {})) {
      if (!qs || !boxId.startsWith(`p${page}-`)) continue;
      out.push(...qs);
    }
    return out;
  }, [questions.data, page]);

  const selected: Question | null = useMemo(() => {
    if (!selectedEntry) return null;
    for (const qs of Object.values(questions.data ?? {})) {
      const hit = qs?.find((q) => q.entry_id === selectedEntry);
      if (hit) return hit;
    }
    return null;
  }, [selectedEntry, questions.data]);

  const referenceAnswer = selected?.answer ?? null;

  function handleSendToPipeline() {
    if (!selected) return;
    setPipelineResult(null);
    setCompareResult(null);
    ask.mutate(
      { name: pipelineName, question: selected.text },
      {
        onSuccess: (data) => {
          setPipelineResult(data);
          success(`${data.chunks.length} Chunks + Antwort von ${pipelineName}`);
        },
        onError: (e) => error(e instanceof Error ? e.message : "Pipeline fehlgeschlagen"),
      },
    );
  }

  function handleCompare() {
    if (!referenceAnswer || !pipelineResult?.answer) return;
    compare.mutate(
      { reference: referenceAnswer, candidate: pipelineResult.answer },
      {
        onSuccess: (data) => setCompareResult(data),
        onError: (e) => error(e instanceof Error ? e.message : "Vergleich fehlgeschlagen"),
      },
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar — same chrome as Extract / Synthesise. */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>

      <div className="flex flex-1 min-h-0">
        {/* ── Left: questions list + similar block. ──────────────── */}
        <div
          className="flex-1 flex flex-col border-r border-slate-200 bg-white overflow-y-auto min-w-0"
          data-testid="compare-left"
        >
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
            <span className={T.tinyBold}>Fragen auf Seite {page}</span>
            <span className={`${T.bodyMuted} ml-auto`}>
              {questionsOnPage.length} Frage(n)
            </span>
          </div>
          {questionsOnPage.length === 0 ? (
            <p className={`${T.bodyMuted} italic px-4 py-3`}>Keine Fragen auf dieser Seite.</p>
          ) : (
            <ul className="list-none p-0 flex flex-col">
              {questionsOnPage.map((q) => {
                const active = q.entry_id === selectedEntry;
                return (
                  <li
                    key={q.entry_id}
                    onClick={() => setSelectedEntry(q.entry_id)}
                    className={`px-4 py-2 cursor-pointer border-b border-slate-100 hover:bg-blue-50 ${
                      active ? "bg-blue-100" : ""
                    }`}
                    data-testid={`compare-question-${q.entry_id}`}
                  >
                    <p className="text-[14px] leading-snug text-slate-800 whitespace-pre-wrap">
                      {q.text}
                    </p>
                    {q.answer && (
                      <p className={`${T.tiny} text-emerald-700 mt-0.5 line-clamp-2`}>
                        Antwort: {q.answer}
                      </p>
                    )}
                    <p className={`${T.tiny} text-slate-400 font-mono mt-0.5`}>{q.box_id}</p>
                  </li>
                );
              })}
            </ul>
          )}

          {/* Similar block — appears under the list once a Q is selected. */}
          {selected && (
            <div className="px-4 py-3 border-t border-slate-200 bg-slate-50">
              <span className={T.tinyBold}>
                Ähnliche Fragen im Dokument
                {similar.data?.embedder ? " (BM25 + Cosine)" : " (BM25)"}
              </span>
              {similar.isPending ? (
                <p className={`${T.bodyMuted} italic`}>Lade…</p>
              ) : similar.data && similar.data.hits.length > 0 ? (
                <ul className="list-none p-0 flex flex-col gap-2 mt-1">
                  {similar.data.hits.map((h) => (
                    <SimilarHitRow key={h.entry_id} hit={h} embedder={similar.data!.embedder} />
                  ))}
                </ul>
              ) : (
                <p className={`${T.bodyMuted} italic`}>Keine ähnlichen Fragen gefunden.</p>
              )}
            </div>
          )}
        </div>

        {/* ── Middle: pipeline runner + comparison. ───────────────── */}
        <div
          className="flex-1 flex flex-col border-r border-slate-200 bg-slate-50 overflow-y-auto px-4 py-4 gap-3 min-w-0"
          data-testid="compare-middle"
        >
          <div className="flex items-center gap-2">
            <span className={T.tinyBold}>Pipeline</span>
            <select
              value={pipelineName}
              onChange={(e) => {
                setPipelineName(e.target.value);
                setPipelineResult(null);
                setCompareResult(null);
              }}
              className="px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 text-xs"
              data-testid="compare-pipeline-select"
            >
              {(pipelines.data ?? []).map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available}>
                  {p.label}
                  {!p.available ? ` — ${p.note ?? "nicht verfügbar"}` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!selected || ask.isPending}
              onClick={handleSendToPipeline}
              className={`ml-auto px-3 py-1.5 rounded bg-blue-600 text-white ${T.bodyMedium} hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed`}
              data-testid="compare-send"
            >
              {ask.isPending ? "Sende…" : "▶ Senden"}
            </button>
          </div>

          {!selected && (
            <p className={`${T.bodyMuted} italic`}>
              Wähle links eine Frage, um sie an die Pipeline zu schicken.
            </p>
          )}

          {selected && (
            <>
              <div className="rounded border border-slate-200 bg-white px-3 py-2">
                <span className={T.tinyBold}>Frage</span>
                <p className="text-[14px] leading-snug">{selected.text}</p>
                {referenceAnswer && (
                  <>
                    <span className={`${T.tinyBold} mt-1 block`}>Referenz-Antwort (lokal)</span>
                    <p className={`${T.body} text-emerald-800`}>{referenceAnswer}</p>
                  </>
                )}
                {!referenceAnswer && (
                  <p className={`${T.bodyMuted} italic mt-1`}>
                    Noch keine Referenz-Antwort. Generiere sie in der Synthesise-Tab.
                  </p>
                )}
              </div>

              {pipelineResult && (
                <div className="rounded border border-slate-200 bg-white px-3 py-2 flex flex-col gap-1">
                  <span className={T.tinyBold}>{pipelineName} — Antwort</span>
                  <p className={`${T.body} whitespace-pre-wrap`}>{pipelineResult.answer}</p>
                  <details className="mt-1">
                    <summary className={`${T.tiny} cursor-pointer text-slate-600`}>
                      Chunks ({pipelineResult.chunks.length})
                    </summary>
                    <ul className="list-none p-0 mt-1 flex flex-col gap-1">
                      {pipelineResult.chunks.map((c) => (
                        <li
                          key={c.chunk_id}
                          className="rounded border border-slate-200 bg-slate-50 px-2 py-1"
                        >
                          <p className={`${T.tiny} text-slate-500`}>
                            {c.title ?? c.chunk_id} · score {c.score.toFixed(3)}
                          </p>
                          <p className={`${T.body} whitespace-pre-wrap`}>{c.chunk}</p>
                        </li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}

              <button
                type="button"
                disabled={!pipelineResult || !referenceAnswer || compare.isPending}
                onClick={handleCompare}
                className={`px-3 py-1.5 rounded bg-emerald-600 text-white ${T.bodyMedium} hover:bg-emerald-700 disabled:bg-slate-300 disabled:cursor-not-allowed self-start`}
                data-testid="compare-compare"
              >
                {compare.isPending ? "Vergleiche…" : "▶ Vergleichen"}
              </button>

              {compareResult && (
                <div className="rounded border border-slate-200 bg-white px-3 py-2 flex flex-col gap-2">
                  <span className={T.tinyBold}>Ähnlichkeit Referenz ↔ {pipelineName}</span>
                  <ScoreBar label="Cosine" value={compareResult.cosine} />
                  <ScoreBar label="BM25" value={compareResult.bm25} />
                  {!compareResult.embedder && (
                    <p className={`${T.tiny} text-amber-700`}>
                      Cosine = 0 weil Azure-Embeddings nicht konfiguriert sind.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Right: thin controls strip — page nav + lock (same as Synthesise). ── */}
        <aside
          className="w-[280px] flex flex-col gap-3 bg-white px-4 py-4 overflow-y-auto flex-shrink-0"
          data-testid="compare-sidebar"
        >
          <div className="flex flex-col gap-2">
            <div
              className={`flex items-center justify-between gap-2 ${T.tiny} text-slate-600 whitespace-nowrap`}
            >
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded bg-red-200 shrink-0" aria-hidden="true" />
                Keine Fragen
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded bg-green-200 shrink-0" aria-hidden="true" />
                Mit Fragen
              </span>
            </div>

            <div className="flex items-stretch gap-1">
              <button
                type="button"
                aria-label="Vorherige Seite"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-2 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                data-testid="compare-page-prev"
              >
                ◀
              </button>
              <button
                type="button"
                aria-label={`Seite ${page} von ${totalPages}, ${pageGridOpen ? "Liste schließen" : "Liste öffnen"}`}
                aria-expanded={pageGridOpen}
                onClick={() => setPageGridOpen((p) => !p)}
                className={`${comparePageBtnClasses(pagesWithQuestions.has(page), true)} flex-1 !h-9 flex items-center justify-center gap-1 ${T.body} transition-colors`}
                data-testid="compare-page-grid-toggle"
              >
                <span>
                  Seite {page} / {totalPages}
                </span>
                <motion.span
                  aria-hidden="true"
                  animate={{ rotate: pageGridOpen ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  ▾
                </motion.span>
              </button>
              <button
                type="button"
                aria-label="Nächste Seite"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                className="px-2 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                data-testid="compare-page-next"
              >
                ▶
              </button>
            </div>

            <AnimatePresence initial={false}>
              {pageGridOpen && (
                <motion.div
                  key="compare-page-grid"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  style={{ overflow: "hidden" }}
                >
                  <div
                    className="grid grid-cols-5 gap-1 pt-1 max-h-64 overflow-y-auto pr-1"
                    role="group"
                    aria-label="Page navigation"
                  >
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                      <button
                        key={p}
                        type="button"
                        aria-label={`Seite ${p}`}
                        aria-pressed={p === page}
                        className={`${comparePageBtnClasses(pagesWithQuestions.has(p), p === page)} transition-colors`}
                        onClick={() => {
                          setPage(p);
                          setPageGridOpen(false);
                          setSelectedEntry(null);
                          setPipelineResult(null);
                          setCompareResult(null);
                        }}
                        data-testid={`compare-page-btn-${p}`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button
            type="button"
            aria-label={
              approvedPages.has(page) ? "Diese Seite entsperren" : "Diese Seite sperren"
            }
            onClick={handleToggleApprove}
            className={
              approvedPages.has(page)
                ? `${T.body} px-3 py-1.5 rounded border border-blue-400 bg-blue-100 text-blue-800 hover:bg-blue-200`
                : `${T.body} px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`
            }
            data-testid="compare-page-lock"
          >
            {approvedPages.has(page) ? "🔓 Diese Seite entsperren" : "🔒 Diese Seite sperren"}
          </button>
        </aside>
      </div>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }): JSX.Element {
  const pct = Math.max(0, Math.min(1, value));
  const w = `${(pct * 100).toFixed(0)}%`;
  const color =
    pct >= 0.8 ? "bg-emerald-500" : pct >= 0.5 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className={`${T.tinyBold} w-14`}>{label}</span>
      <div className="flex-1 h-2 rounded bg-slate-100 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: w }} />
      </div>
      <span className={`${T.tiny} font-mono w-12 text-right`}>{value.toFixed(2)}</span>
    </div>
  );
}

function SimilarHitRow({ hit, embedder }: { hit: SimilarHit; embedder: boolean }): JSX.Element {
  return (
    <li className="rounded border border-slate-200 bg-white px-2 py-1">
      <p className="text-[13px] leading-snug">{hit.text}</p>
      <p className={`${T.tiny} text-slate-400 font-mono`}>{hit.box_id}</p>
      <div className="flex items-center gap-2 mt-1">
        <ScoreBar label="BM25" value={hit.bm25_score} />
      </div>
      {embedder && (
        <div className="flex items-center gap-2">
          <ScoreBar label="Cos" value={hit.cosine_score} />
        </div>
      )}
      {hit.chunk && (
        <details className="mt-1">
          <summary className={`${T.tiny} cursor-pointer text-slate-600`}>Chunk</summary>
          <p className={`${T.tiny} text-slate-700 whitespace-pre-wrap mt-0.5`}>
            {hit.chunk.slice(0, 400)}
            {hit.chunk.length > 400 ? "…" : ""}
          </p>
        </details>
      )}
    </li>
  );
}

export function Comparison(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <ComparisonInner slug={slug!} token={token} />;
}

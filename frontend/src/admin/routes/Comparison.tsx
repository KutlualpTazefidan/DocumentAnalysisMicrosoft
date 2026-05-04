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
  useDeleteMicrosoftSource,
  useMicrosoftSources,
  usePipelines,
  useRefreshMicrosoftSources,
  useSimilarQuestions,
  useUploadMicrosoftSource,
  type AskResponse,
  type KnowledgeSource,
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
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
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
  const microsoftSources = useMicrosoftSources(token);
  const refreshSources = useRefreshMicrosoftSources(token);
  const uploadSource = useUploadMicrosoftSource(token);
  const deleteSource = useDeleteMicrosoftSource(token);

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
      {
        name: pipelineName,
        question: selected.text,
        source: pipelineName === "microsoft" ? selectedSource ?? undefined : undefined,
      },
      {
        onSuccess: (data) => {
          setPipelineResult(data);
          success(`${data.chunks.length} Chunks + Antwort von ${pipelineName}`);
        },
        onError: (e) => error(e instanceof Error ? e.message : "Pipeline fehlgeschlagen"),
      },
    );
  }

  async function handleUploadSource(file: File) {
    const proceed = window.confirm(
      `"${file.name}" hochladen?\n\nDokument-Intelligence + Embeddings + ` +
        `Indexierung kosten Azure-Credits. Bei größeren PDFs kann das spürbar werden.`,
    );
    if (!proceed) return;
    try {
      const src = await uploadSource.mutateAsync(file);
      setSelectedSource(src.slug);
      success(`"${src.filename}" hochgeladen — bereit zum Ingestieren`);
    } catch (e) {
      error(e instanceof Error ? e.message : "Upload fehlgeschlagen");
    }
  }

  async function handleDeleteSource(slug: string, filename: string, external: boolean) {
    const msg = external
      ? `⚠ "${filename}" ist ein vorhandener Azure-Index — Löschen entfernt ihn auch ` +
        "auf Azure (nicht nur lokal). Andere Nutzer verlieren den Zugriff. Wirklich löschen?"
      : `"${filename}" und seinen Azure-Index wirklich löschen?`;
    if (!window.confirm(msg)) return;
    try {
      await deleteSource.mutateAsync(slug);
      if (selectedSource === slug) setSelectedSource(null);
      success(`"${filename}" entfernt`);
    } catch (e) {
      error(e instanceof Error ? e.message : "Löschen fehlgeschlagen");
    }
  }

  async function handleRefreshSources() {
    try {
      const list = await refreshSources.mutateAsync();
      success(`${list.length} Quelle(n) — Azure abgeglichen`);
    } catch (e) {
      error(e instanceof Error ? e.message : "Aktualisieren fehlgeschlagen");
    }
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
        {/* ── Pane 1: Questions list (narrow). ──────────────────── */}
        <div
          className="w-[300px] flex-shrink-0 flex flex-col border-r border-slate-200 bg-white overflow-y-auto"
          data-testid="compare-left"
        >
          <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 sticky top-0 bg-white z-10">
            <span className={T.tinyBold}>Fragen auf Seite {page}</span>
            <span className={`${T.bodyMuted} ml-auto`}>{questionsOnPage.length}</span>
          </div>
          {questionsOnPage.length === 0 ? (
            <p className={`${T.bodyMuted} italic px-3 py-3`}>Keine Fragen auf dieser Seite.</p>
          ) : (
            <ul className="list-none p-0 flex flex-col">
              {questionsOnPage.map((q) => {
                const active = q.entry_id === selectedEntry;
                return (
                  <li
                    key={q.entry_id}
                    onClick={() => setSelectedEntry(q.entry_id)}
                    className={`px-3 py-2 cursor-pointer border-b border-slate-100 hover:bg-blue-50 transition-colors ${
                      active ? "bg-blue-50 border-l-4 border-l-blue-500" : "border-l-4 border-l-transparent"
                    }`}
                    data-testid={`compare-question-${q.entry_id}`}
                  >
                    <p className="text-[13px] leading-snug text-slate-800 whitespace-pre-wrap">
                      {q.text}
                    </p>
                    {q.answer && (
                      <p className={`${T.tiny} text-emerald-700 mt-0.5 line-clamp-2`}>
                        ✓ Antwort vorhanden
                      </p>
                    )}
                    <p className={`${T.tiny} text-slate-400 font-mono mt-0.5`}>{q.box_id}</p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* ── Pane 2: NEW — Detail / similar + their chunks. ──── */}
        <div
          className="flex-1 flex flex-col border-r border-slate-200 bg-slate-50 overflow-y-auto min-w-0"
          data-testid="compare-detail"
        >
          {!selected ? (
            <div className="flex-1 flex items-center justify-center">
              <p className={`${T.bodyMuted} italic px-4`}>
                Wähle links eine Frage, um Details und ähnliche Fragen zu sehen.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3 px-4 py-4">
              {/* Selected question card */}
              <section className="rounded-lg border-2 border-blue-300 bg-white shadow-sm overflow-hidden">
                <header className="px-4 py-2 bg-blue-50 border-b border-blue-200 flex items-center gap-2">
                  <span className={`${T.tinyBold} text-blue-900 uppercase tracking-wide`}>
                    Ausgewählte Frage
                  </span>
                  <span className={`${T.tiny} font-mono text-blue-700 ml-auto`}>
                    {selected.box_id}
                  </span>
                </header>
                <div className="px-4 py-3 flex flex-col gap-2">
                  <p className="text-[15px] leading-snug text-slate-800 whitespace-pre-wrap">
                    {selected.text}
                  </p>
                  {referenceAnswer ? (
                    <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2">
                      <span className={`${T.tinyBold} text-emerald-900`}>
                        Referenz-Antwort (lokal)
                      </span>
                      <p className={`${T.body} text-emerald-900 whitespace-pre-wrap mt-0.5`}>
                        {referenceAnswer}
                      </p>
                    </div>
                  ) : (
                    <p className={`${T.tiny} text-amber-700 italic`}>
                      Noch keine Referenz-Antwort. Generiere sie in der Synthesise-Tab.
                    </p>
                  )}
                </div>
              </section>

              {/* Similar questions — section header */}
              <header className="flex items-center gap-2 mt-2">
                <span className={`${T.tinyBold} uppercase tracking-wide text-slate-700`}>
                  Ähnliche Fragen im Dokument
                </span>
                {similar.data && (
                  <span className={`${T.tiny} text-slate-500`}>
                    {similar.data.hits.length} ·{" "}
                    {similar.data.embedder ? "BM25 + Cosine" : "BM25"}
                  </span>
                )}
              </header>

              {similar.isPending ? (
                <p className={`${T.bodyMuted} italic`}>Lade…</p>
              ) : similar.data && similar.data.hits.length > 0 ? (
                <div className="flex flex-col gap-3">
                  {similar.data.hits.map((h, i) => (
                    <SimilarCard
                      key={h.entry_id}
                      hit={h}
                      rank={i + 1}
                      embedder={similar.data!.embedder}
                    />
                  ))}
                </div>
              ) : (
                <p className={`${T.bodyMuted} italic`}>Keine ähnlichen Fragen gefunden.</p>
              )}
            </div>
          )}
        </div>

        {/* ── Pane 3: pipeline runner + comparison. ───────────────── */}
        <div
          className="w-[440px] flex-shrink-0 flex flex-col border-r border-slate-200 bg-white overflow-y-auto px-4 py-4 gap-3"
          data-testid="compare-middle"
        >
          <header className="flex items-center gap-2">
            <span className={`${T.tinyBold} uppercase tracking-wide text-slate-700`}>
              {pipelines.data?.find((p) => p.name === pipelineName)?.label ?? pipelineName}
            </span>
            {pipelineName === "microsoft" && selectedSource && (
              <span className={`${T.tiny} text-slate-500`}>
                Quelle: <code>{selectedSource}</code>
              </span>
            )}
            <button
              type="button"
              disabled={
                !selected ||
                ask.isPending ||
                (pipelineName === "microsoft" && !selectedSource)
              }
              onClick={handleSendToPipeline}
              className={`ml-auto px-3 py-1.5 rounded bg-blue-600 text-white ${T.bodyMedium} hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed`}
              data-testid="compare-send"
            >
              {ask.isPending ? "Sende…" : "▶ Senden"}
            </button>
          </header>

          {!selected && (
            <p className={`${T.bodyMuted} italic`}>
              Wähle links eine Frage, um sie an die Pipeline zu schicken.
            </p>
          )}

          {selected && pipelineName === "microsoft" && !selectedSource && (
            <p className={`${T.tiny} text-amber-700 bg-amber-50 rounded p-2`}>
              ⚠ Wähle rechts eine Microsoft-Wissensquelle aus oder lade ein PDF hoch,
              bevor du senden kannst.
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

          <hr className="border-slate-200" />

          {/* Pipeline selector — moved here from the middle pane. */}
          <div className="flex flex-col gap-1">
            <label className={`${T.tinyBold} uppercase tracking-wide text-slate-700`}>
              Pipeline
            </label>
            <select
              value={pipelineName}
              onChange={(e) => {
                setPipelineName(e.target.value);
                setPipelineResult(null);
                setCompareResult(null);
              }}
              className={`${T.body} px-2 py-1.5 rounded border border-slate-300 bg-white text-slate-800`}
              data-testid="compare-pipeline-select"
            >
              {(pipelines.data ?? []).map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available}>
                  {p.label}
                  {!p.available ? ` — ${p.note ?? "nicht verfügbar"}` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Microsoft-only knowledge-source panel. */}
          {pipelineName === "microsoft" && (
            <MicrosoftSourcesPanel
              sources={microsoftSources.data ?? []}
              loading={microsoftSources.isPending}
              selected={selectedSource}
              onSelect={(slug) => {
                setSelectedSource(slug);
                setPipelineResult(null);
                setCompareResult(null);
              }}
              onUpload={handleUploadSource}
              onDelete={handleDeleteSource}
              onRefresh={handleRefreshSources}
              uploadPending={uploadSource.isPending}
              deletePending={deleteSource.isPending}
              refreshPending={refreshSources.isPending}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function MicrosoftSourcesPanel({
  sources,
  loading,
  selected,
  onSelect,
  onUpload,
  onDelete,
  onRefresh,
  uploadPending,
  deletePending,
  refreshPending,
}: {
  sources: KnowledgeSource[];
  loading: boolean;
  selected: string | null;
  onSelect: (slug: string) => void;
  onUpload: (file: File) => void;
  onDelete: (slug: string, filename: string, external: boolean) => void;
  onRefresh: () => void;
  uploadPending: boolean;
  deletePending: boolean;
  refreshPending: boolean;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <span className={`${T.tinyBold} uppercase tracking-wide text-slate-700 flex-1`}>
          Wissensquellen
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshPending}
          className="p-1 rounded text-slate-500 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-40"
          title="Mit Azure abgleichen"
          aria-label="Wissensquellen aktualisieren"
          data-testid="ms-sources-refresh"
        >
          <RefreshIcon spinning={refreshPending} />
        </button>
      </div>

      {loading ? (
        <p className={`${T.bodyMuted} italic`}>Lade…</p>
      ) : sources.length === 0 ? (
        <p className={`${T.bodyMuted} italic`}>Noch keine Quellen.</p>
      ) : (
        <ul className="list-none p-0 flex flex-col gap-1">
          {sources.map((s) => {
            const active = s.slug === selected;
            return (
              <li
                key={s.slug}
                className={`rounded border ${
                  active ? "border-blue-400 bg-blue-50" : "border-slate-200 bg-white"
                } px-2 py-1.5 flex flex-col gap-0.5`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(s.slug)}
                  className="text-left flex items-center gap-1"
                  data-testid={`ms-source-${s.slug}`}
                >
                  <span className={`${T.body} truncate flex-1`} title={s.filename}>
                    {s.filename}
                  </span>
                  {s.external && (
                    <span
                      className="px-1 py-0.5 rounded bg-purple-100 text-purple-700 text-[9px] uppercase font-bold tracking-wide"
                      title="Auf Azure vorgefunden — nicht selbst hochgeladen"
                    >
                      extern
                    </span>
                  )}
                  <SourceStateChip state={s.state} />
                </button>
                <div className="flex items-center justify-between">
                  <span className={`${T.tiny} text-slate-400`}>
                    {s.pages > 0
                      ? `${s.pages} Seite${s.pages === 1 ? "" : "n"}`
                      : s.external
                        ? "extern"
                        : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => onDelete(s.slug, s.filename, s.external ?? false)}
                    disabled={deletePending}
                    className="text-red-600 hover:bg-red-50 rounded px-1 text-[11px] disabled:opacity-40"
                    aria-label={`${s.filename} entfernen`}
                  >
                    🗑
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <label
        className={`${T.body} text-center px-3 py-1.5 rounded border border-blue-300 bg-blue-50 text-blue-800 hover:bg-blue-100 cursor-pointer ${
          uploadPending ? "opacity-40 cursor-wait" : ""
        }`}
        data-testid="ms-upload"
      >
        {uploadPending ? "Lädt…" : "▲ PDF hochladen"}
        <input
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          disabled={uploadPending}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = "";
          }}
        />
      </label>
    </div>
  );
}

function RefreshIcon({ spinning }: { spinning: boolean }): JSX.Element {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={spinning ? "animate-spin" : ""}
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}

function SourceStateChip({
  state,
}: {
  state: KnowledgeSource["state"];
}): JSX.Element {
  const STYLE: Record<KnowledgeSource["state"], string> = {
    uploaded: "bg-slate-200 text-slate-700",
    analyzed: "bg-amber-200 text-amber-800",
    chunked: "bg-amber-200 text-amber-800",
    embedded: "bg-amber-200 text-amber-800",
    indexed: "bg-emerald-200 text-emerald-800",
    error: "bg-red-200 text-red-800",
  };
  const LABEL: Record<KnowledgeSource["state"], string> = {
    uploaded: "neu",
    analyzed: "1/4",
    chunked: "2/4",
    embedded: "3/4",
    indexed: "✓",
    error: "✗",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${STYLE[state]}`}>
      {LABEL[state]}
    </span>
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

function SimilarCard({
  hit,
  rank,
  embedder,
}: {
  hit: SimilarHit;
  rank: number;
  embedder: boolean;
}): JSX.Element {
  // Combined score for the "headline" — weighted same way the backend
  // ranks. Drives the ribbon colour so users see the verdict at a
  // glance without reading both bars.
  const combined = embedder
    ? 0.4 * hit.bm25_score + 0.6 * hit.cosine_score
    : hit.bm25_score;
  const ribbon =
    combined >= 0.7
      ? "bg-emerald-500"
      : combined >= 0.4
        ? "bg-amber-500"
        : "bg-slate-400";

  return (
    <article
      className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden flex"
      data-testid={`similar-card-${hit.entry_id}`}
    >
      {/* Rank ribbon — coloured by combined score. */}
      <div
        className={`${ribbon} text-white text-[11px] font-bold w-7 flex-shrink-0 flex items-start justify-center pt-2`}
      >
        #{rank}
      </div>

      {/* Question side */}
      <div className="flex-1 px-3 py-2 border-r border-slate-100 min-w-0 flex flex-col gap-1">
        <p className="text-[13px] leading-snug text-slate-800 whitespace-pre-wrap">
          {hit.text}
        </p>
        <p className={`${T.tiny} text-slate-400 font-mono`}>{hit.box_id}</p>
        <div className="flex flex-col gap-0.5 mt-1">
          <ScoreBar label="BM25" value={hit.bm25_score} />
          {embedder && <ScoreBar label="Cos" value={hit.cosine_score} />}
        </div>
      </div>

      {/* Chunk side */}
      <div className="flex-1 px-3 py-2 bg-slate-50 min-w-0 flex flex-col">
        <span className={`${T.tinyBold} text-slate-600 uppercase tracking-wide`}>
          Chunk
        </span>
        {hit.chunk ? (
          <p
            className={`${T.tiny} text-slate-700 whitespace-pre-wrap mt-0.5 line-clamp-6 leading-relaxed`}
            title={hit.chunk}
          >
            {hit.chunk}
          </p>
        ) : (
          <p className={`${T.tiny} italic text-slate-400 mt-0.5`}>kein Inhalt</p>
        )}
      </div>
    </article>
  );
}

export function Comparison(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <ComparisonInner slug={slug!} token={token} />;
}

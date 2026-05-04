import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { DocStepTabs } from "../components/DocStepTabs";
import { HtmlPreview } from "../components/HtmlPreview";
import { LlmServerPanel } from "../components/LlmServerPanel";
import { QuestionList } from "../components/QuestionList";
import { StageIndicator } from "../components/StageIndicator";
import { useHtml } from "../hooks/useExtract";
import { useLlmStream } from "../hooks/useLlmStream";
import {
  streamGenerate,
  useAnswerBox,
  useDeprecateQuestion,
  useEditAnswer,
  useGenerateBox,
  useQuestions,
  useRefineQuestion,
  type StreamHandles,
  type StreamEvent,
} from "../hooks/useSynthesise";
import { rewriteImageSources, sliceHtmlByPage } from "../lib/extractHtml";
import { apiBase } from "../api/adminClient";
import { loadCurrentPage, saveCurrentPage } from "../lib/currentPage";
import { useMineru } from "../hooks/useExtract";
import { T } from "../styles/typography";

/**
 * Synthesise tab — admin LLM-driven question generation per element.
 *
 * Layout: read-only HTML preview on the left, per-box question sidebar
 * on the right. Click a box on the preview → sidebar shows that box's
 * existing questions + Generate / Generate page / Generate file
 * buttons. Streaming generations are cancellable.
 *
 * See spec: docs/superpowers/specs/2026-05-03-synthesise-ui-design.md
 */

function synthPageBtnClasses(hasQuestions: boolean, isActive: boolean): string {
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

function SynthesiseInner({ slug, token }: InnerProps): JSX.Element {
  const html = useHtml(slug, token);
  const mineru = useMineru(slug, token);
  const questions = useQuestions(slug, token);
  const generateBox = useGenerateBox(slug, token);
  const answerBox = useAnswerBox(slug, token);
  const editAnswer = useEditAnswer(slug, token);
  const refine = useRefineQuestion(slug, token);
  const deprecate = useDeprecateQuestion(slug, token);
  const llmStream = useLlmStream(token);
  const { success, error } = useToast();

  const [page, setPage] = useState<number>(() => loadCurrentPage(slug));
  const [highlight, setHighlight] = useState<string | null>(null);
  const [pageGridOpen, setPageGridOpen] = useState(false);

  // Streaming state.
  const streamRef = useRef<StreamHandles | null>(null);
  const [streaming, setStreaming] = useState<{
    scope: "page" | "doc";
    completed: number;
    accepted: number;
  } | null>(null);

  useEffect(() => {
    saveCurrentPage(slug, page);
  }, [slug, page]);

  // Slice html by current page so the preview only shows that page.
  const visibleHtml = useMemo(
    () =>
      rewriteImageSources(
        sliceHtmlByPage(html.data ?? "", page),
        apiBase(),
        slug,
      ),
    [html.data, page, slug],
  );

  // Page count derived from the mineru elements (box_id format pN-bM).
  const totalPages = useMemo<number>(() => {
    const pages = new Set<number>();
    for (const el of mineru.data?.elements ?? []) {
      const m = el.box_id.match(/^p(\d+)-/);
      if (m) pages.add(parseInt(m[1], 10));
    }
    return pages.size > 0 ? Math.max(...pages) : 1;
  }, [mineru.data]);

  // Pages that already have at least one (non-deprecated) question.
  // Drives the green/red colouring in the page-grid widget.
  const pagesWithQuestions = useMemo<Set<number>>(() => {
    const out = new Set<number>();
    for (const [boxId, qs] of Object.entries(questions.data ?? {})) {
      if (!qs || qs.length === 0) continue;
      const m = boxId.match(/^p(\d+)-/);
      if (m) out.add(parseInt(m[1], 10));
    }
    return out;
  }, [questions.data]);

  const questionsForBox = highlight
    ? (questions.data?.[highlight] ?? [])
    : [];

  // Metadata about the highlighted box, derived from mineru.json.
  // Element type comes from the first tag in the snippet (h1, p,
  // table, figure, …); page + box index come from the box_id format
  // pN-bM. Position from data-x/data-y attrs the extractor stamped.
  const highlightMeta = useMemo(() => {
    if (!highlight) return null;
    const el = mineru.data?.elements.find((e) => e.box_id === highlight);
    if (!el) return null;
    const pageMatch = highlight.match(/^p(\d+)-b(\d+)/);
    const tagMatch = el.html_snippet.match(/<\s*([a-zA-Z][\w-]*)/);
    const xMatch = el.html_snippet.match(/data-x="(-?\d+)"/);
    const yMatch = el.html_snippet.match(/data-y="(-?\d+)"/);
    // Strip tags for a short text preview.
    const text = el.html_snippet.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
    return {
      page: pageMatch ? parseInt(pageMatch[1], 10) : null,
      boxIndex: pageMatch ? parseInt(pageMatch[2], 10) : null,
      tag: tagMatch ? tagMatch[1].toLowerCase() : null,
      x: xMatch ? parseInt(xMatch[1], 10) : null,
      y: yMatch ? parseInt(yMatch[1], 10) : null,
      preview: text.slice(0, 90) + (text.length > 90 ? "…" : ""),
    };
  }, [highlight, mineru.data]);

  function handleStreamEvent(ev: StreamEvent) {
    if (ev.event === "completed") {
      setStreaming((s) =>
        s === null
          ? s
          : {
              ...s,
              completed: s.completed + 1,
              accepted: s.accepted + (ev.accepted ?? 0),
            },
      );
    }
    if (ev.event === "done" || ev.event === "cancelled") {
      const wasStreaming = streamRef.current !== null;
      streamRef.current = null;
      setStreaming(null);
      void questions.refetch();
      if (ev.event === "done" && wasStreaming) success("Fragen generiert");
      if (ev.event === "cancelled") success("Generierung abgebrochen");
    }
    if (ev.event === "error") {
      streamRef.current = null;
      setStreaming(null);
      error(ev.detail || "Streaming-Fehler");
    }
  }

  function startStream(scope: "page" | "doc") {
    if (streamRef.current) return;
    setStreaming({ scope, completed: 0, accepted: 0 });
    streamRef.current = streamGenerate(
      slug,
      token,
      scope === "page" ? { page } : {},
      handleStreamEvent,
    );
  }

  function cancelStream() {
    streamRef.current?.controller.abort();
    streamRef.current = null;
    setStreaming(null);
    void questions.refetch();
  }

  async function handleGenerateBox() {
    if (!highlight) return;
    try {
      const res = await generateBox.mutateAsync(highlight);
      if (res.accepted === 0 && res.skipped_reason) {
        success(`Keine Fragen — ${res.skipped_reason}`);
      } else {
        success(`${res.accepted} neue Frage(n)`);
      }
    } catch (e) {
      error(e instanceof Error ? e.message : "Generierung fehlgeschlagen");
    }
  }

  async function handleAnswerBox() {
    if (!highlight) return;
    try {
      const res = await answerBox.mutateAsync(highlight);
      if (res.answered === 0 && res.skipped_reason) {
        success(`Keine Antworten — ${res.skipped_reason}`);
      } else {
        success(`${res.answered} Antwort(en) generiert`);
      }
    } catch (e) {
      error(e instanceof Error ? e.message : "Antwort-Generierung fehlgeschlagen");
    }
  }

  // ── Duplicate detection ──────────────────────────────────────────
  // Mirrors the backend's normalize_for_dedup (NFKC casefold + strip
  // punctuation + collapse whitespace) so the UI count matches what
  // the backend would consider duplicates. Box-scoped: same wording
  // across different boxes is intentionally not flagged.
  function planDuplicates(predicate: (boxId: string) => boolean): string[] {
    const toRemove: string[] = [];
    for (const [boxId, qs] of Object.entries(questions.data ?? {})) {
      if (!predicate(boxId)) continue;
      if (!qs || qs.length < 2) continue;
      const seen = new Set<string>();
      for (const q of qs) {
        const n = q.text
          .normalize("NFKC")
          .toLocaleLowerCase()
          .replace(/[^\p{L}\p{N}\s]/gu, " ")
          .replace(/\s+/g, " ")
          .trim();
        if (!n) continue;
        if (seen.has(n)) toRemove.push(q.entry_id);
        else seen.add(n);
      }
    }
    return toRemove;
  }

  const docDuplicateIds = useMemo(
    () => planDuplicates(() => true),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions.data],
  );
  const pageDuplicateIds = useMemo(
    () => planDuplicates((boxId) => boxId.startsWith(`p${page}-`)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions.data, page],
  );
  const boxDuplicateIds = useMemo(
    () => (highlight ? planDuplicates((boxId) => boxId === highlight) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions.data, highlight],
  );

  async function removeDuplicates(ids: string[], scopeLabel: string) {
    if (ids.length === 0) return;
    if (!window.confirm(`${ids.length} doppelte Frage(n) ${scopeLabel} löschen?`)) return;
    let removed = 0;
    for (const id of ids) {
      try {
        await deprecate.mutateAsync(id);
        removed += 1;
      } catch (e) {
        error(e instanceof Error ? e.message : `Löschen ${id} fehlgeschlagen`);
      }
    }
    if (removed > 0) success(`${removed} Duplikat(e) entfernt`);
    void questions.refetch();
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar: DocStepTabs left, page/file Generate actions right ── */}
      <div className="flex items-center gap-2 px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug} />
        <div className="ml-auto flex items-center gap-2">
          {docDuplicateIds.length > 0 && (
            <button
              type="button"
              disabled={deprecate.isPending}
              onClick={() => removeDuplicates(docDuplicateIds, "im Dokument")}
              className={`px-3 py-1.5 rounded border border-amber-300 bg-amber-50 text-amber-900 ${T.bodyMedium} hover:bg-amber-100 disabled:opacity-40 disabled:cursor-not-allowed`}
              data-testid="synthesise-remove-duplicates-doc"
            >
              🧹 {docDuplicateIds.length} Duplikat(e) im Dokument
            </button>
          )}
          <button
            type="button"
            disabled={streaming !== null || generateBox.isPending}
            onClick={() => startStream("page")}
            className={`px-3 py-1.5 rounded border border-navy-600 bg-navy-700 text-white ${T.bodyMedium} hover:bg-navy-600 disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            ⚡ Fragen für die Seite generieren
          </button>
          <button
            type="button"
            disabled={streaming !== null || generateBox.isPending}
            onClick={() => {
              if (window.confirm("Fragen für die ganze Datei generieren?")) {
                startStream("doc");
              }
            }}
            className={`px-3 py-1.5 rounded border border-navy-600 bg-navy-700 text-white ${T.bodyMedium} hover:bg-navy-600 disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            ⚡ Fragen für die ganze Datei generieren
          </button>
        </div>
      </div>

      {/* ── Three-pane content: HTML | Questions | Controls ─────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Left: HTML preview pane — read-only. Page nav lives in the
            right controls strip; no toolbar here so the preview gets
            maximum vertical space. */}
        <div className="flex-1 flex flex-col border-r border-slate-200 min-w-0">
          <div className="flex-1 bg-white">
            <HtmlPreview
              html={visibleHtml}
              onClickElement={setHighlight}
              highlightedBoxId={highlight}
            />
          </div>
        </div>

        {/* Middle: Questions pane — full size, mirrors Extract's HTML pane */}
        <div
          className="flex-1 flex flex-col border-r border-slate-200 min-w-0 bg-white"
          data-testid="synthesise-questions"
        >
          <div className="flex items-center gap-2 px-8 py-2 border-b border-slate-200 bg-slate-50">
            <span className={T.tinyBold}>Ausgewählte Box:</span>
            <span className={`${T.body} font-mono`}>
              {highlight ?? <em className="text-slate-400">keine</em>}
            </span>
            <span className={`${T.bodyMuted} ml-auto`}>
              {highlight ? `${questionsForBox.length} Frage(n)` : ""}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {!highlight ? (
              <p className={`${T.bodyMuted} italic`}>
                Klicke ein Element im HTML-Bereich, um die Fragen zu sehen.
              </p>
            ) : (
              <QuestionList
                questions={questionsForBox}
                onRefine={async (entryId, text) => {
                  try {
                    await refine.mutateAsync({ questionId: entryId, text });
                    success("Frage aktualisiert");
                  } catch (e) {
                    error(e instanceof Error ? e.message : "Aktualisieren fehlgeschlagen");
                  }
                }}
                onDeprecate={async (entryId) => {
                  try {
                    await deprecate.mutateAsync(entryId);
                    success("Frage gelöscht");
                  } catch (e) {
                    error(e instanceof Error ? e.message : "Löschen fehlgeschlagen");
                  }
                }}
                onEditAnswer={async (entryId, text) => {
                  try {
                    await editAnswer.mutateAsync({ entryId, text });
                    success(text ? "Antwort aktualisiert" : "Antwort gelöscht");
                  } catch (e) {
                    error(e instanceof Error ? e.message : "Antwort speichern fehlgeschlagen");
                  }
                }}
                disabled={refine.isPending || deprecate.isPending || editAnswer.isPending}
              />
            )}
          </div>
        </div>

        {/* Right: thin controls strip — page nav + vLLM + Generate */}
        <aside
          className="w-[280px] flex flex-col gap-3 bg-white px-4 py-4 overflow-y-auto flex-shrink-0"
          data-testid="synthesise-sidebar"
        >
          {/* Page navigation, modelled after Extract's sidebar widget.
              Prev | "Seite X / Y" toggle | Next; toggle expands a grid
              of every page coloured by whether it already has any
              generated questions. */}
          <div className="flex flex-col gap-2">
            <div className={`flex items-center justify-between gap-2 ${T.tiny} text-slate-600 whitespace-nowrap`}>
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
                data-testid="synth-page-prev"
              >
                ◀
              </button>
              <button
                type="button"
                aria-label={`Seite ${page} von ${totalPages}, ${pageGridOpen ? "Liste schließen" : "Liste öffnen"}`}
                aria-expanded={pageGridOpen}
                onClick={() => setPageGridOpen((p) => !p)}
                className={`${synthPageBtnClasses(pagesWithQuestions.has(page), true)} flex-1 !h-9 flex items-center justify-center gap-1 ${T.body} transition-colors`}
                data-testid="synth-page-grid-toggle"
              >
                <span>Seite {page} / {totalPages}</span>
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
                data-testid="synth-page-next"
              >
                ▶
              </button>
            </div>

            <AnimatePresence initial={false}>
              {pageGridOpen && (
                <motion.div
                  key="synth-page-grid"
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
                        className={`${synthPageBtnClasses(pagesWithQuestions.has(p), p === page)} transition-colors`}
                        onClick={() => {
                          setPage(p);
                          setPageGridOpen(false);
                        }}
                        data-testid={`synth-page-btn-${p}`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <hr className="border-slate-200" />

          <LlmServerPanel token={token} />

          <hr className="border-slate-200" />

          {/* Box metadata — what "diese Box" refers to. */}
          <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 flex flex-col gap-1">
            <span className={T.tinyBold}>Ausgewählte Box</span>
            {highlightMeta ? (
              <>
                <div className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 ${T.body}`}>
                  <span className="font-mono text-slate-800">{highlight}</span>
                  {highlightMeta.tag && (
                    <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px] uppercase tracking-wide">
                      {highlightMeta.tag}
                    </span>
                  )}
                </div>
                <span className={T.bodyMuted}>
                  Seite {highlightMeta.page ?? "?"} · Box {highlightMeta.boxIndex ?? "?"}
                  {highlightMeta.x != null && highlightMeta.y != null
                    ? ` · ${highlightMeta.x},${highlightMeta.y}`
                    : ""}
                </span>
                <span className={`${T.bodyMuted} italic line-clamp-2`}>
                  {highlightMeta.preview || <em>(leer)</em>}
                </span>
                <span className={`${T.bodyMuted} mt-0.5`}>
                  {questionsForBox.length} bestehende Frage(n)
                </span>
              </>
            ) : (
              <span className={`${T.bodyMuted} italic`}>
                Klicke ein Element im HTML-Bereich, um es auszuwählen.
              </span>
            )}
          </div>

          <button
            type="button"
            aria-label="Fragen für diese Box generieren"
            disabled={!highlight || generateBox.isPending || streaming !== null}
            onClick={handleGenerateBox}
            className={`w-full px-3 py-1.5 rounded bg-blue-600 text-white ${T.bodyMedium} hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed`}
          >
            {generateBox.isPending ? "…" : "⚡ Fragen für diese Box generieren"}
          </button>

          <button
            type="button"
            aria-label="Antworten für diese Box generieren"
            disabled={
              !highlight ||
              answerBox.isPending ||
              streaming !== null ||
              questionsForBox.length === 0
            }
            onClick={handleAnswerBox}
            className={`w-full px-3 py-1.5 rounded bg-emerald-600 text-white ${T.bodyMedium} hover:bg-emerald-700 disabled:bg-slate-300 disabled:cursor-not-allowed`}
            data-testid="synthesise-answer-box"
          >
            {answerBox.isPending ? "…" : "📝 Antworten für diese Box generieren"}
          </button>

          {/* Box-scoped dedup — only the highlighted box's questions. */}
          {boxDuplicateIds.length > 0 && (
            <button
              type="button"
              aria-label="Doppelte Fragen in dieser Box entfernen"
              disabled={deprecate.isPending}
              onClick={() => removeDuplicates(boxDuplicateIds, "in dieser Box")}
              className={`w-full px-3 py-1.5 rounded border border-amber-400 bg-amber-50 text-amber-900 ${T.bodyMedium} hover:bg-amber-100 disabled:opacity-40 disabled:cursor-not-allowed`}
              data-testid="synthesise-remove-duplicates-box"
            >
              🧹 {boxDuplicateIds.length} Duplikat(e) in dieser Box
            </button>
          )}

          {/* Page-scoped dedup — restricts the bulk delete to boxes
              on the currently-viewed page. Doc-scoped dedup lives in
              the topbar so it stays reachable from any page. */}
          {pageDuplicateIds.length > 0 && (
            <button
              type="button"
              aria-label="Doppelte Fragen auf dieser Seite entfernen"
              disabled={deprecate.isPending}
              onClick={() => removeDuplicates(pageDuplicateIds, `auf Seite ${page}`)}
              className={`w-full px-3 py-1.5 rounded border border-amber-400 bg-amber-50 text-amber-900 ${T.bodyMedium} hover:bg-amber-100 disabled:opacity-40 disabled:cursor-not-allowed`}
              data-testid="synthesise-remove-duplicates-page"
            >
              🧹 {pageDuplicateIds.length} Duplikat(e) auf Seite {page}
            </button>
          )}

          {streaming && (
            <div className="rounded border border-blue-200 bg-blue-50 p-2 flex flex-col gap-1">
              <span className={T.tinyBold}>
                {streaming.scope === "page"
                  ? `Generiere Seite ${page}…`
                  : "Generiere ganze Datei…"}
              </span>
              <span className={T.body}>
                {streaming.completed} Elemente, {streaming.accepted} Fragen
              </span>
              <button
                type="button"
                aria-label="Generierung abbrechen"
                onClick={cancelStream}
                className="px-2 py-1 rounded bg-red-600 text-white text-xs hover:bg-red-700"
                data-testid="synthesise-cancel"
              >
                Abbrechen
              </button>
            </div>
          )}
        </aside>
      </div>

      {/* Bottom-left lifecycle pill — same component the Extract page
          uses, fed by the local vLLM lifecycle (loading / loaded /
          unloading / failed). Click to open the timeline. */}
      <StageIndicator state={llmStream} />
    </div>
  );
}

export function Synthesise(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <SynthesiseInner slug={slug!} token={token} />;
}

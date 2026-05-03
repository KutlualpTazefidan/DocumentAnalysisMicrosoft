import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { DocStepTabs } from "../components/DocStepTabs";
import { HtmlPreview } from "../components/HtmlPreview";
import { QuestionList } from "../components/QuestionList";
import { useHtml } from "../hooks/useExtract";
import {
  streamGenerate,
  useDeprecateQuestion,
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

interface InnerProps {
  slug: string;
  token: string;
}

function SynthesiseInner({ slug, token }: InnerProps): JSX.Element {
  const html = useHtml(slug, token);
  const mineru = useMineru(slug, token);
  const questions = useQuestions(slug, token);
  const generateBox = useGenerateBox(slug, token);
  const refine = useRefineQuestion(slug, token);
  const deprecate = useDeprecateQuestion(slug, token);
  const { success, error } = useToast();

  const [page, setPage] = useState<number>(() => loadCurrentPage(slug));
  const [highlight, setHighlight] = useState<string | null>(null);

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

  const questionsForBox = highlight
    ? (questions.data?.[highlight] ?? [])
    : [];

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

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>

      {/* ── Three-pane content ─────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* HTML preview pane — read-only */}
        <div className="flex-1 flex flex-col border-r border-slate-200 min-w-0">
          <div className="flex items-center gap-2 p-2 border-b border-slate-200 bg-slate-50">
            <button
              type="button"
              aria-label="Vorherige Seite"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ◀
            </button>
            <span className={T.body}>
              Seite {page} / {totalPages}
            </span>
            <button
              type="button"
              aria-label="Naechste Seite"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className="px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ▶
            </button>
          </div>
          <div className="flex-1 bg-white">
            <HtmlPreview
              html={visibleHtml}
              onClickElement={setHighlight}
              highlightedBoxId={highlight}
            />
          </div>
        </div>

        {/* Sidebar — questions panel */}
        <aside
          className="w-[360px] flex flex-col gap-3 bg-white px-4 py-4 overflow-y-auto flex-shrink-0"
          data-testid="synthesise-sidebar"
        >
          <div className="flex flex-col gap-1">
            <span className={T.tinyBold}>Ausgewaehlte Box</span>
            <span className={`${T.body} font-mono`}>
              {highlight ?? <em className="text-slate-400">keine</em>}
            </span>
          </div>

          <button
            type="button"
            aria-label="Fuer diese Box generieren"
            disabled={!highlight || generateBox.isPending || streaming !== null}
            onClick={handleGenerateBox}
            className={`w-full px-3 py-1.5 rounded bg-blue-600 text-white ${T.bodyMedium} hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed`}
          >
            {generateBox.isPending ? "…" : "⚡ Fuer diese Box generieren"}
          </button>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={streaming !== null || generateBox.isPending}
              onClick={() => startStream("page")}
              className={`px-3 py-1.5 rounded border border-slate-300 text-slate-700 ${T.bodyMedium} hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              ⚡ Seite
            </button>
            <button
              type="button"
              disabled={streaming !== null || generateBox.isPending}
              onClick={() => {
                if (window.confirm("Fuer das ganze Dokument generieren?")) {
                  startStream("doc");
                }
              }}
              className={`px-3 py-1.5 rounded border border-slate-300 text-slate-700 ${T.bodyMedium} hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              ⚡ Datei
            </button>
          </div>

          {streaming && (
            <div className="rounded border border-blue-200 bg-blue-50 p-2 flex flex-col gap-1">
              <span className={T.tinyBold}>
                {streaming.scope === "page"
                  ? `Generiere Seite ${page}…`
                  : "Generiere Datei…"}
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

          <hr className="border-slate-200" />

          <div className="flex flex-col gap-2">
            <span className={T.tinyBold}>
              Fragen ({questionsForBox.length})
            </span>
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
                    success("Frage geloescht");
                  } catch (e) {
                    error(e instanceof Error ? e.message : "Loeschen fehlgeschlagen");
                  }
                }}
                disabled={refine.isPending || deprecate.isPending}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export function Synthesise(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <SynthesiseInner slug={slug!} token={token} />;
}

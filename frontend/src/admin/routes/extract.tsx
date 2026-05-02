// frontend/src/admin/routes/extract.tsx
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { loadCurrentPage, saveCurrentPage } from "../lib/currentPage";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { getDoc } from "../api/docs";
import { T } from "../styles/typography";

import { BoxLegend } from "../components/BoxLegend";
import { ExtractDiagnose } from "../components/ExtractDiagnose";
import { BoxOverlay } from "../components/BoxOverlay";
import { DocStepTabs } from "../components/DocStepTabs";
import { HtmlEditor } from "../components/HtmlEditor";
import { PdfPage } from "../components/PdfPage";
import { StageIndicator } from "../components/StageIndicator";
import { sliceHtmlByPage } from "../lib/extractHtml";
import { useSegments } from "../hooks/useSegments";
import {
  streamExtract,
  useExportSourceElements,
  useExtractRegion,
  useHtml,
  useMineru,
  usePutHtml,
} from "../hooks/useExtract";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import { loadConf, effectiveThreshold } from "../lib/confThreshold";
import type { WorkerEvent } from "../types/domain";

interface Props {
  token: string;
}

function reducer(state: StreamState, ev: WorkerEvent): StreamState {
  return applyEvent(state, ev);
}

// ── Approval helpers (v1: localStorage) ───────────────────────────────────────

function approvedPagesKey(slug: string): string {
  return `extract.approved.${slug}`;
}

function loadApprovedPages(slug: string): Set<number> {
  try {
    const raw = localStorage.getItem(approvedPagesKey(slug));
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as number[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveApprovedPages(slug: string, pages: Set<number>): void {
  localStorage.setItem(approvedPagesKey(slug), JSON.stringify([...pages]));
}

// ── Page-state helpers ─────────────────────────────────────────────────────────

type PageState = "no-extraction" | "extracted" | "approved";

function pageStateFor(
  pageNum: number,
  extractedPages: Set<number>,
  approvedPages: Set<number>,
): PageState {
  if (approvedPages.has(pageNum)) return "approved";
  if (extractedPages.has(pageNum)) return "extracted";
  return "no-extraction";
}

function pageButtonClasses(state: PageState, isActive: boolean): string {
  const base = `w-10 h-10 rounded ${T.body} font-medium flex items-center justify-center transition-colors`;
  const ring = isActive ? " ring-2 ring-blue-500" : "";
  switch (state) {
    case "approved":
      return `${base} bg-blue-100 hover:bg-blue-200 text-blue-800${ring}`;
    case "extracted":
      return `${base} bg-green-100 hover:bg-green-200 text-green-800${ring}`;
    case "no-extraction":
    default:
      return `${base} bg-red-100 hover:bg-red-200 text-red-800${ring}`;
  }
}

export function ExtractRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const segments = useSegments(slug ?? "", token);
  const html = useHtml(slug ?? "", token);
  const mineru = useMineru(slug ?? "", token);
  const putHtml = usePutHtml(slug ?? "", token);
  const exportSrc = useExportSourceElements(slug ?? "", token);
  const extractRegion = useExtractRegion(slug ?? "", token);

  // Current page is persisted per-doc so segment/extract tabs stay in sync.
  const [page, setPageRaw] = useState(() => loadCurrentPage(slug ?? ""));
  const setPage = useCallback(
    (p: number) => {
      setPageRaw(p);
      saveCurrentPage(slug ?? "", p);
    },
    [slug],
  );
  const [gridOpen, setGridOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [approvedPages, setApprovedPages] = useState<Set<number>>(() =>
    loadApprovedPages(slug ?? ""),
  );
  // Zoom persisted under admin.extract.scale, mirroring segment's pattern.
  const [scale, setScale] = useState<number>(() => {
    const stored = parseFloat(localStorage.getItem("admin.extract.scale") ?? "");
    return Number.isFinite(stored) && stored >= 0.25 && stored <= 4 ? stored : 1.2;
  });
  const debounceRef = useRef<number | null>(null);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);
  const { success, error } = useToast();

  function persistScale(s: number) {
    const clamped = Math.min(4, Math.max(0.25, parseFloat(s.toFixed(2))));
    setScale(clamped);
    localStorage.setItem("admin.extract.scale", String(clamped));
  }

  function handleHtmlChange(next: string) {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      putHtml.mutate(next);
    }, 300);
  }

  useEffect(() => () => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
  }, []);

  async function runExtract() {
    setRunning(true);
    try {
      for await (const ev of streamExtract(slug!, token)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
      await html.refetch();
      await mineru.refetch();
    } finally {
      setRunning(false);
    }
  }

  async function runExtractThisPage() {
    setRunning(true);
    try {
      for await (const ev of streamExtract(slug!, token, page)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
      await html.refetch();
      await mineru.refetch();
    } finally {
      setRunning(false);
    }
  }

  function handleExport() {
    exportSrc.mutate(undefined, {
      onSuccess: () => success("Exported sourceelements.json"),
      onError: (err) => error((err as Error).message),
    });
  }

  function handleClickElement(boxId: string) {
    setHighlight(boxId);
    const target = (segments.data?.boxes ?? []).find((b) => b.box_id === boxId);
    if (target) setPage(target.page);
  }

  function handleReExtractBox() {
    if (!highlight) return;
    if (!window.confirm(`Box ${highlight} re-extrahieren?`)) return;
    extractRegion.mutate(highlight, {
      onSuccess: (r) => success(`re-extracted ${r.box_id}`),
      onError: (err) => error((err as Error).message),
    });
  }

  function handleToggleApprove() {
    const next = new Set(approvedPages);
    if (next.has(page)) {
      next.delete(page);
    } else {
      next.add(page);
    }
    setApprovedPages(next);
    saveApprovedPages(slug ?? "", next);
  }

  const rasterDpi = segments.data?.raster_dpi ?? 144;
  const boxScale = (scale * 72) / rasterDpi;

  // Total page count from DocMeta — present even before segmentation runs,
  // so the page-grid shows every page in the doc immediately on import.
  // Falls back to highest page seen in boxes if doc meta isn't loaded yet.
  const docMeta = useQuery({
    queryKey: ["doc", slug],
    queryFn: () => getDoc(slug!, token),
    enabled: !!slug,
  });
  const totalPages = useMemo(() => {
    if (docMeta.data?.pages) return docMeta.data.pages;
    const boxes = segments.data?.boxes ?? [];
    return boxes.length > 0 ? Math.max(...boxes.map((b) => b.page)) : 1;
  }, [docMeta.data, segments.data]);

  // Read per-page conf threshold from the segment-route's localStorage key (display only).
  const confState = useMemo(() => loadConf(slug ?? ""), [slug]);
  const confThresholdForPage = effectiveThreshold(confState, page);

  const boxesOnPage = useMemo(() => {
    const allOnPage = (segments.data?.boxes ?? []).filter((b) => b.page === page);
    // Apply the same confidence filter as segment route (display only — extraction is not filtered).
    return allOnPage.filter(
      (b) => b.kind !== "discard" && (b.manually_activated || b.confidence >= confThresholdForPage),
    );
  }, [segments.data, page, confThresholdForPage]);

  // ── Compute which pages have extractions ──────────────────────────────
  const extractedPages = useMemo<Set<number>>(() => {
    const elements = mineru.data?.elements ?? [];
    const pages = new Set<number>();
    for (const el of elements) {
      // box_id format: pN-bM  →  page = N
      const match = el.box_id.match(/^p(\d+)-/);
      if (match) pages.add(parseInt(match[1], 10));
    }
    return pages;
  }, [mineru.data]);

  // ── Slice the full-doc HTML to only the current page ──────────────────
  // TODO: backend per-page persistence (v1: display-only slice; full doc is authoritative)
  const visibleHtml = useMemo(
    () => sliceHtmlByPage(html.data ?? "", page),
    [html.data, page],
  );

  // ── Saving status derived from putHtml mutation state ─────────────────
  const savingStatus = putHtml.isPending
    ? "Saving…"
    : putHtml.isSuccess
    ? "Saved"
    : null;

  // ── Action buttons — right-aligned in top bar ─────────────────────────
  // Re-extract-this-box and Re-extract-this-page live in the side pane now;
  // the top bar holds only the doc-level actions (Alle Seiten / Export).
  const actionButtons = (
    <div className="flex items-center gap-1.5">
      <button
        aria-label="Re-extract all"
        className={`${T.body} px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:bg-gray-400 disabled:cursor-not-allowed`}
        onClick={runExtract}
        disabled={running}
      >
        Alle Seiten extrahieren
      </button>
      <button
        aria-label="Export sourceelements.json"
        className={`${T.body} px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed`}
        onClick={handleExport}
        disabled={exportSrc.isPending}
      >
        Export
      </button>
      {/* Save-state indicator (HTML editor). Extraction progress lives in the
          StageIndicator pill at bottom-left, not duplicated here. */}
      {!running && savingStatus && (
        <span className={`${T.body} text-navy-200 ml-1`}>{savingStatus}</span>
      )}
    </div>
  );

  // ── Top bar ──────────────────────────────────────────────────────────────
  const topBar = (
    <div className="flex items-center justify-between px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
      <DocStepTabs slug={slug!} />
      {actionButtons}
    </div>
  );

  const hasExtraction = !!html.data;

  return (
    <div className="flex flex-col h-full">
      {topBar}

      {/* ── Content row ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* PDF pane: wrapper-with-absolute-inner pattern from segment */}
        <div className="flex-[3] relative min-w-0">
          {/* Floating colour legend, top-left */}
          <BoxLegend />
          {/* Floating zoom control, top-right */}
          <div className="absolute top-4 right-4 z-20 flex items-center gap-1 bg-white/90 backdrop-blur border border-slate-300 rounded shadow-sm px-2 py-1">
            <button
              aria-label="Zoom out"
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-slate-700 disabled:opacity-30 disabled:cursor-not-allowed"
              onClick={() => persistScale(scale - 0.1)}
              disabled={scale <= 0.25}
            >
              −
            </button>
            <button
              aria-label="Reset zoom"
              className={`px-1 ${T.mono} text-slate-700 hover:text-slate-900 w-12 text-center`}
              onClick={() => persistScale(1.2)}
              title="Reset to 120%"
            >
              {Math.round(scale * 100)}%
            </button>
            <button
              aria-label="Zoom in"
              className="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-slate-700 disabled:opacity-30 disabled:cursor-not-allowed"
              onClick={() => persistScale(scale + 0.1)}
              disabled={scale >= 4}
            >
              +
            </button>
          </div>
          {/* Scrollable inner container */}
          <div className="absolute inset-0 overflow-auto p-4">
            <div className="flex justify-center">
              <PdfPage slug={slug!} token={token} page={page} scale={scale}>
                {boxesOnPage.map((b) => (
                  <BoxOverlay
                    key={b.box_id}
                    box={b}
                    selected={highlight === b.box_id}
                    // Boxes are read-only in extract view — click to highlight only
                    onSelect={(id) => setHighlight((prev) => (prev === id ? null : id))}
                    onChange={() => {}}
                    scale={boxScale}
                  />
                ))}
              </PdfPage>
            </div>
          </div>
          {/* Empty-state hint card — overlays the PDF pane when nothing extracted yet */}
          {!hasExtraction && (
            <div
              data-testid="empty-extract-hint"
              className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none"
            >
              <div className="bg-white/95 backdrop-blur border border-slate-200 rounded-lg shadow-sm p-4 max-w-xs text-center space-y-1 pointer-events-auto">
                <p className={`${T.body} text-slate-700 font-medium`}>Noch keine Extraktion.</p>
                <p className={T.cardSubtle}>
                  Klicke „Alle Seiten extrahieren" oben rechts, oder „Diese Seite extrahieren" in der Seitenleiste.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* HTML editor pane — shows only the current page's content */}
        <div className="flex-[2] flex flex-col border-l border-slate-200 min-w-0">
          <HtmlEditor html={visibleHtml} onChange={handleHtmlChange} onClickElement={handleClickElement} />
        </div>

        {/* Sidebar — colored page-button grid */}
        <aside className="w-[280px] border-l border-slate-200 flex flex-col gap-3 bg-white overflow-y-auto px-4 py-4 flex-shrink-0">
          {/* Legend strip — single line, always visible */}
          <div className={`flex items-center justify-between gap-1 ${T.tiny} text-slate-600 whitespace-nowrap`}>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded bg-red-200 shrink-0" aria-hidden="true" />
              Nicht extr.
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded bg-green-200 shrink-0" aria-hidden="true" />
              Extrahiert
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded bg-blue-200 shrink-0" aria-hidden="true" />
              Gesperrt
            </span>
          </div>

          {/* Single page button — toggles the grid below */}
          <button
            aria-label={`Seite ${page} von ${totalPages}, ${gridOpen ? "Liste schließen" : "Liste öffnen"}`}
            aria-expanded={gridOpen}
            onClick={() => setGridOpen((p) => !p)}
            className={`${pageButtonClasses(pageStateFor(page, extractedPages, approvedPages), true)} w-full !h-9 flex items-center justify-center gap-1 ${T.body} transition-colors`}
            data-testid="extract-page-grid-toggle"
          >
            <span>Seite {page} / {totalPages}</span>
            <motion.span
              aria-hidden="true"
              animate={{ rotate: gridOpen ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              ▾
            </motion.span>
          </button>

          {/* Animated grid (expand/collapse) */}
          <AnimatePresence initial={false}>
            {gridOpen && (
              <motion.div
                key="extract-page-grid"
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
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => {
                    const state = pageStateFor(p, extractedPages, approvedPages);
                    return (
                      <button
                        key={p}
                        aria-label={`Page ${p}`}
                        aria-pressed={p === page}
                        className={`${pageButtonClasses(state, p === page)} transition-colors`}
                        onClick={() => {
                          setPage(p);
                          setGridOpen(false);
                        }}
                        data-testid={`page-btn-${p}`}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <hr className="border-slate-200" />

          {/* Per-page extract */}
          <button
            aria-label="Re-extract this page"
            title={
              approvedPages.has(page)
                ? "Seite ist gesperrt. Erst entsperren um neu zu extrahieren."
                : undefined
            }
            className={`w-full ${T.body} px-3 py-1.5 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed`}
            onClick={runExtractThisPage}
            disabled={running || approvedPages.has(page)}
          >
            {running ? "Läuft…" : "Diese Seite extrahieren"}
          </button>

          {/* Per-box extract — only when a box is selected */}
          <button
            aria-label="Re-extract this box"
            title={
              approvedPages.has(page)
                ? "Seite ist gesperrt. Erst entsperren um neu zu extrahieren."
                : !highlight
                ? "Klicke zuerst eine Box im PDF an"
                : undefined
            }
            className={`w-full ${T.body} px-3 py-1.5 rounded border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 disabled:opacity-40 disabled:cursor-not-allowed`}
            onClick={handleReExtractBox}
            disabled={!highlight || running || approvedPages.has(page)}
          >
            Diese Box extrahieren
          </button>

          {/* Lock / unlock current page (was "Diese Seite genehmigen") */}
          <button
            aria-label={approvedPages.has(page) ? "Diese Seite entsperren" : "Diese Seite sperren"}
            className={
              approvedPages.has(page)
                ? `${T.body} px-3 py-1.5 rounded border border-blue-400 bg-blue-100 text-blue-800 hover:bg-blue-200 w-full`
                : `${T.body} px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 w-full`
            }
            onClick={handleToggleApprove}
          >
            {approvedPages.has(page) ? "🔓 Diese Seite entsperren" : "🔒 Diese Seite sperren"}
          </button>

          {/* Conf filter status indicator */}
          <p
            className={`${T.bodyMuted} text-center`}
            data-testid="conf-filter-status"
          >
            Filter aktiv: Conf ≥ {confThresholdForPage.toFixed(2)}
          </p>

          <p className={`${T.body} text-slate-400 text-center`}>
            {boxesOnPage.length} boxes on page {page}
          </p>

          {/* Diagnose section — what the worker decided for THIS page. */}
          <ExtractDiagnose
            diagnostics={mineru.data?.diagnostics ?? []}
            currentPage={page}
          />
        </aside>
      </div>

      <StageIndicator state={streamState} />
    </div>
  );
}

export function Extract() {
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <ExtractRoute token={token} />;
}

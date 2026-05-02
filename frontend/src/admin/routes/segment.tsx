// frontend/src/admin/routes/segment.tsx
import { useCallback, useMemo, useReducer, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";

import { BoxLegend } from "../components/BoxLegend";
import { BoxOverlay } from "../components/BoxOverlay";
import { DocStepTabs } from "../components/DocStepTabs";
import { PdfPage } from "../components/PdfPage";
import {
  PropertiesSidebar,
  loadApprovedSegmentPages,
  saveApprovedSegmentPages,
} from "../components/PropertiesSidebar";
import { StageIndicator } from "../components/StageIndicator";
import { useBoxHotkeys } from "../hooks/useBoxHotkeys";
import {
  useCreateBox,
  useDeleteBox,
  useMergeBoxes,
  useMergeBoxDown,
  useMergeBoxUp,
  useUnmergeBoxDown,
  useUnmergeBoxUp,
  useResetBox,
  useResetPage,
  useSegments,
  useSplitBox,
  useUpdateBox,
} from "../hooks/useSegments";
import { streamSegment } from "../hooks/useExtract";
import { getDoc } from "../api/docs";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import {
  loadConf,
  saveConf,
  effectiveThreshold,
  type ConfThresholdState,
} from "../lib/confThreshold";
import type { BoxKind, WorkerEvent } from "../types/domain";

interface Props {
  token: string;
}

function reducer(state: StreamState, ev: WorkerEvent): StreamState {
  return applyEvent(state, ev);
}

export function SegmentRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState(1);
  // Zoom is persisted in localStorage so it survives page reloads + applies
  // to every page in this and future docs (single global preference).
  const [scale, setScale] = useState<number>(() => {
    const stored = parseFloat(localStorage.getItem("admin.segment.scale") ?? "");
    return Number.isFinite(stored) && stored >= 0.25 && stored <= 4 ? stored : 1.5;
  });
  function persistScale(s: number) {
    const clamped = Math.min(4, Math.max(0.25, parseFloat(s.toFixed(2))));
    setScale(clamped);
    localStorage.setItem("admin.segment.scale", String(clamped));
  }
  const segments = useSegments(slug ?? "", token);
  // Bbox coords are pixel-space at the rasterization DPI used for YOLO
  // inference. To overlay them on a PDF.js viewport rendered at `scale`
  // (where scale=1 means 72 DPI / native PDF units), multiply by
  // (scale * 72 / raster_dpi). Default raster_dpi=144 covers legacy files.
  const rasterDpi = segments.data?.raster_dpi ?? 144;
  const boxScale = (scale * 72) / rasterDpi;
  const update = useUpdateBox(slug ?? "", token);
  // useMergeBoxes kept for future use; not wired to UI
  useMergeBoxes(slug ?? "", token);
  const split = useSplitBox(slug ?? "", token);
  const newBox = useCreateBox(slug ?? "", token);
  const del = useDeleteBox(slug ?? "", token);
  const resetPageMut = useResetPage(slug ?? "", token);
  const resetBoxMut = useResetBox(slug ?? "", token);
  const mergeDownMut = useMergeBoxDown(slug ?? "", token);
  const mergeUpMut = useMergeBoxUp(slug ?? "", token);
  const unmergeDownMut = useUnmergeBoxDown(slug ?? "", token);
  const unmergeUpMut = useUnmergeBoxUp(slug ?? "", token);
  const [selected, setSelected] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);
  const { success, error } = useToast();

  // Range inputs for no-segments-yet view
  const [rangeStart, setRangeStart] = useState(1);
  const [rangeEnd, setRangeEnd] = useState(10);

  // Mehr-Seiten dialog state
  const [moreDialogOpen, setMoreDialogOpen] = useState(false);
  const [moreStart, setMoreStart] = useState(1);
  const [moreEnd, setMoreEnd] = useState(10);

  // Per-page confidence threshold state (from localStorage)
  const [confState, setConfState] = useState<ConfThresholdState>(() =>
    loadConf(slug ?? ""),
  );
  const [showDeactivated, setShowDeactivated] = useState(false);

  // Approved pages (segment-route localStorage key)
  const [approvedPages, setApprovedPages] = useState<Set<number>>(() =>
    loadApprovedSegmentPages(slug ?? ""),
  );

  // Total page count from DocMeta (falls back to highest page seen in boxes)
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

  // Effective threshold for the currently viewed page
  const currentThreshold = effectiveThreshold(confState, page);

  const allBoxesOnPage = useMemo(
    () => (segments.data?.boxes ?? []).filter((b) => b.page === page),
    [segments.data, page],
  );

  // Active boxes are those not discarded AND (manually activated OR above threshold).
  // Deactivated ones are hidden unless `showDeactivated` is on.
  const activeBoxIds = useMemo(
    () => new Set(
      allBoxesOnPage
        .filter((b) => b.kind !== "discard" && (b.manually_activated || b.confidence >= currentThreshold))
        .map((b) => b.box_id),
    ),
    [allBoxesOnPage, currentThreshold],
  );

  // What the parent sees as "on page" for things like box count.
  const boxesOnPage = useMemo(
    () => allBoxesOnPage.filter((b) => activeBoxIds.has(b.box_id)),
    [allBoxesOnPage, activeBoxIds],
  );

  // Boxes that will be rendered: active always, deactivated only when showDeactivated.
  const visibleBoxes = useMemo(
    () => (showDeactivated ? allBoxesOnPage : boxesOnPage),
    [showDeactivated, allBoxesOnPage, boxesOnPage],
  );

  // Compute segmented pages (pages that have at least one box)
  const segmentedPages = useMemo<Set<number>>(() => {
    const boxes = segments.data?.boxes ?? [];
    return new Set(boxes.map((b) => b.page));
  }, [segments.data]);

  const focused = useMemo(
    () => (segments.data?.boxes ?? []).find((b) => b.box_id === selected) ?? null,
    [segments.data, selected],
  );

  function handleSelect(boxId: string) {
    setSelected((prev) => (prev === boxId ? null : boxId));
  }

  async function runSegmentRange(start?: number, end?: number) {
    setRunning(true);
    try {
      for await (const ev of streamSegment(slug!, token, start, end)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`segmented ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
      await segments.refetch();
    } finally {
      setRunning(false);
    }
  }

  function runSegment() {
    return runSegmentRange(rangeStart, rangeEnd);
  }

  const openMoreDialog = useCallback(() => {
    const boxes = segments.data?.boxes ?? [];
    const maxPage = boxes.length > 0 ? Math.max(...boxes.map((b) => b.page)) : 0;
    const nextStart = Math.min(maxPage + 1, totalPages);
    const nextEnd = Math.min(nextStart + 9, totalPages);
    setMoreStart(nextStart);
    setMoreEnd(nextEnd);
    setMoreDialogOpen(true);
  }, [segments.data, totalPages]);

  async function handleMoreSegment() {
    setMoreDialogOpen(false);
    await runSegmentRange(moreStart, moreEnd);
  }

  // Confidence threshold handlers
  function handlePageThresholdChange(value: number) {
    const next = { ...confState, perPage: { ...confState.perPage, [page]: value } };
    setConfState(next);
    saveConf(slug ?? "", next);
  }

  function handleDefaultThresholdChange(value: number) {
    const next = { ...confState, default: value };
    setConfState(next);
    saveConf(slug ?? "", next);
  }

  function handleClearPageOverride() {
    const { [page]: _removed, ...rest } = confState.perPage;
    const next = { ...confState, perPage: rest };
    setConfState(next);
    saveConf(slug ?? "", next);
  }

  function handleToggleApprove() {
    const next = new Set(approvedPages);
    if (next.has(page)) {
      next.delete(page);
    } else {
      next.add(page);
    }
    setApprovedPages(next);
    saveApprovedSegmentPages(slug ?? "", next);
  }

  function handleDeactivate() {
    if (focused) {
      update.mutate({
        boxId: focused.box_id,
        patch: { kind: "discard", manually_activated: false },
      });
    }
  }

  function handleActivate() {
    if (focused) {
      const restoredKind: BoxKind = focused.kind === "discard" ? "paragraph" : focused.kind;
      update.mutate({
        boxId: focused.box_id,
        patch: { kind: restoredKind, manually_activated: true },
      });
    }
  }

  function handleResetPage() {
    if (window.confirm(`Alle Boxen auf Seite ${page} zurücksetzen?`)) {
      resetPageMut.mutate(page, {
        onError: (e) => error(e instanceof Error ? e.message : "Reset fehlgeschlagen"),
      });
    }
  }

  function handleResetBox() {
    if (focused) {
      resetBoxMut.mutate(focused.box_id, {
        onError: (e) => error(e instanceof Error ? e.message : "Reset fehlgeschlagen"),
      });
    }
  }

  function handleMergeDown() {
    if (focused) {
      mergeDownMut.mutate(focused.box_id, {
        onError: (e) => {
          const msg = e instanceof Error ? e.message : "Merge down fehlgeschlagen";
          error(msg);
        },
      });
    }
  }

  function handleMergeUp() {
    if (focused) {
      mergeUpMut.mutate(focused.box_id, {
        onError: (e) => {
          const msg = e instanceof Error ? e.message : "Merge up fehlgeschlagen";
          error(msg);
        },
      });
    }
  }

  function handleUnmergeDown() {
    if (focused) {
      unmergeDownMut.mutate(focused.box_id, {
        onError: (e) => {
          const msg = e instanceof Error ? e.message : "Unmerge down fehlgeschlagen";
          error(msg);
        },
      });
    }
  }

  function handleUnmergeUp() {
    if (focused) {
      unmergeUpMut.mutate(focused.box_id, {
        onError: (e) => {
          const msg = e instanceof Error ? e.message : "Unmerge up fehlgeschlagen";
          error(msg);
        },
      });
    }
  }

  useBoxHotkeys({
    enabled: !!focused,
    setKind: (k: BoxKind) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } }),
    split: () => focused && split.mutate({ boxId: focused.box_id, splitY: (focused.bbox[1] + focused.bbox[3]) / 2 }),
    newBox: () => newBox.mutate({ page, bbox: [50, 50, 200, 200], kind: "paragraph" }),
    del: () => focused && del.mutate(focused.box_id),
    deactivate: handleDeactivate,
  });

  if (!segments.data) {
    return (
      <div className="p-6 relative">
        <p>No segmentation yet.</p>
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-1 text-sm">
            Von Seite
            <input
              aria-label="Von Seite"
              type="number"
              min={1}
              max={totalPages}
              value={rangeStart}
              onChange={(e) => setRangeStart(Math.max(1, parseInt(e.target.value, 10) || 1))}
              className="w-16 border rounded px-1 py-0.5 text-sm"
            />
          </label>
          <label className="flex items-center gap-1 text-sm">
            Bis Seite
            <input
              aria-label="Bis Seite"
              type="number"
              min={1}
              max={totalPages}
              value={rangeEnd}
              onChange={(e) => setRangeEnd(Math.max(1, parseInt(e.target.value, 10) || 1))}
              className="w-16 border rounded px-1 py-0.5 text-sm"
            />
          </label>
          <button
            className="bg-blue-600 text-white px-3 py-1 rounded disabled:bg-gray-400"
            onClick={runSegment}
            disabled={running}
          >
            {running ? "Segmenting…" : "Run segmentation"}
          </button>
        </div>
        <StageIndicator state={streamState} />
      </div>
    );
  }

  const hasPageOverride = confState.perPage[page] !== undefined;

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white text-sm border-b border-navy-700 flex-shrink-0">
        <DocStepTabs slug={slug!} />

        {/* Right-aligned group: Confidence input + Show deactivated + action buttons */}
        <div className="flex items-center gap-3 ml-auto text-xs">
          <label className="flex items-center gap-1 text-navy-100 whitespace-nowrap">
            Confidence
            <input
              aria-label="Confidence"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={confState.default.toFixed(2)}
              onChange={(e) => handleDefaultThresholdChange(parseFloat(e.target.value) || 0)}
              className="w-14 border border-navy-600 rounded px-1 py-0.5 text-xs bg-navy-700 text-white text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
          </label>
          <label className="flex items-center gap-1 text-navy-100 cursor-pointer">
            <input
              aria-label="Show deactivated"
              type="checkbox"
              checked={showDeactivated}
              onChange={(e) => setShowDeactivated(e.target.checked)}
              className="accent-blue-400"
            />
            Show deactivated
          </label>
          <button
            aria-label="Mehr Seiten segmentieren"
            className="text-xs px-3 py-1 rounded border border-blue-300 text-blue-200 hover:bg-blue-900 disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={running}
            onClick={openMoreDialog}
          >
            + Mehr Seiten segmentieren
          </button>
          <button
            aria-label="Alle Seiten segmentieren"
            className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded disabled:bg-gray-500 disabled:cursor-not-allowed"
            disabled={running}
            onClick={() => runSegmentRange()}
          >
            {running ? "Running…" : "Alle Seiten segmentieren"}
          </button>
        </div>
      </div>

      {/* ── Content row ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* PDF pane: non-scrolling wrapper holds floating widgets; inner div scrolls */}
        <div className="flex-1 relative min-w-0">
          {/* Floating colour legend, top-left — pinned to wrapper corners */}
          <BoxLegend />
          {/* Floating zoom control, top-right — pinned to wrapper corners */}
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
              className="px-1 text-xs text-slate-700 hover:text-slate-900 font-mono w-12 text-center"
              onClick={() => persistScale(1.5)}
              title="Reset to 150%"
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
          {/* Scrollable inner container — PDF content pans inside here */}
          <div className="absolute inset-0 overflow-auto p-4">
            <div className="flex justify-center">
              <PdfPage slug={slug!} token={token} page={page} scale={scale}>
                {visibleBoxes.map((b) => (
                  <BoxOverlay
                    key={b.box_id}
                    box={b}
                    selected={selected === b.box_id}
                    deactivated={!activeBoxIds.has(b.box_id)}
                    onSelect={handleSelect}
                    onChange={(boxId, bbox) => update.mutate({ boxId, patch: { bbox } })}
                    scale={boxScale}
                  />
                ))}
              </PdfPage>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <PropertiesSidebar
          slug={slug ?? ""}
          selected={focused}
          pageBoxCount={boxesOnPage.length}
          currentPage={page}
          totalPages={totalPages}
          segmentedPages={segmentedPages}
          approvedPages={approvedPages}
          onToggleApprove={handleToggleApprove}
          onResegmentPage={() => runSegmentRange(page, page)}
          onResetPage={handleResetPage}
          running={running}
          onChangeKind={(k) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } })}
          onNewBox={() => newBox.mutate({ page, bbox: [50, 50, 200, 200], kind: "paragraph" })}
          onDeactivate={handleDeactivate}
          onActivate={handleActivate}
          onResetBox={handleResetBox}
          onMergeUp={handleMergeUp}
          onMergeDown={handleMergeDown}
          onUnmergeUp={handleUnmergeUp}
          onUnmergeDown={handleUnmergeDown}
          onPageChange={setPage}
          perPageThreshold={currentThreshold}
          hasOverride={hasPageOverride}
          onPerPageChange={handlePageThresholdChange}
          onClearPerPage={handleClearPageOverride}
        />
      </div>

      <StageIndicator state={streamState} />

      {/* ── Mehr Seiten segmentieren dialog ─────────────────────────── */}
      {moreDialogOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Mehr Seiten segmentieren"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
        >
          <div className="bg-white rounded shadow-lg p-6 flex flex-col gap-4 min-w-[300px]">
            <h3 className="font-semibold text-slate-900">Seiten-Bereich segmentieren</h3>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1 text-sm">
                Von Seite
                <input
                  aria-label="Mehr von Seite"
                  type="number"
                  min={1}
                  max={totalPages}
                  value={moreStart}
                  onChange={(e) => setMoreStart(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  className="w-16 border rounded px-1 py-0.5 text-sm"
                />
              </label>
              <label className="flex items-center gap-1 text-sm">
                Bis Seite
                <input
                  aria-label="Mehr bis Seite"
                  type="number"
                  min={1}
                  max={totalPages}
                  value={moreEnd}
                  onChange={(e) => setMoreEnd(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  className="w-16 border rounded px-1 py-0.5 text-sm"
                />
              </label>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                className="px-3 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50"
                onClick={() => setMoreDialogOpen(false)}
              >
                Abbrechen
              </button>
              <button
                className="px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-500"
                onClick={handleMoreSegment}
              >
                Segmentieren
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function Segment() {
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <SegmentRoute token={token} />;
}

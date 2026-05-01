// frontend/src/admin/routes/segment.tsx
import { useMemo, useReducer, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";

import { BoxLegend } from "../components/BoxLegend";
import { BoxOverlay } from "../components/BoxOverlay";
import { PdfPage } from "../components/PdfPage";
import { PropertiesSidebar } from "../components/PropertiesSidebar";
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
import { streamSegment, streamExtract } from "../hooks/useExtract";
import { getDoc } from "../api/docs";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
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

  // Filter state
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);
  const [showDeactivated, setShowDeactivated] = useState(false);

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

  const allBoxesOnPage = useMemo(
    () => (segments.data?.boxes ?? []).filter((b) => b.page === page),
    [segments.data, page],
  );

  // Active boxes are those not discarded AND (manually activated OR above threshold).
  // Deactivated ones are hidden unless `showDeactivated` is on.
  const activeBoxIds = useMemo(
    () => new Set(
      allBoxesOnPage
        .filter((b) => b.kind !== "discard" && (b.manually_activated || b.confidence >= confidenceThreshold))
        .map((b) => b.box_id),
    ),
    [allBoxesOnPage, confidenceThreshold],
  );

  // What the parent sees as "on page" for things like box count and extraction.
  const boxesOnPage = useMemo(
    () => allBoxesOnPage.filter((b) => activeBoxIds.has(b.box_id)),
    [allBoxesOnPage, activeBoxIds],
  );

  // Boxes that will be rendered: active always, deactivated only when showDeactivated.
  const visibleBoxes = useMemo(
    () => (showDeactivated ? allBoxesOnPage : boxesOnPage),
    [showDeactivated, allBoxesOnPage, boxesOnPage],
  );

  const focused = useMemo(
    () => (segments.data?.boxes ?? []).find((b) => b.box_id === selected) ?? null,
    [segments.data, selected],
  );

  function handleSelect(boxId: string) {
    setSelected((prev) => (prev === boxId ? null : boxId));
  }

  async function runSegment() {
    setRunning(true);
    try {
      for await (const ev of streamSegment(slug!, token)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`segmented ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
      await segments.refetch();
    } finally {
      setRunning(false);
    }
  }

  async function onRunExtractAll() {
    setRunning(true);
    try {
      for await (const ev of streamExtract(slug!, token, undefined)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
    } finally {
      setRunning(false);
    }
  }

  async function onRunExtractThisPage() {
    setRunning(true);
    try {
      for await (const ev of streamExtract(slug!, token, page)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
    } finally {
      setRunning(false);
    }
  }

  function handleDeactivate() {
    if (focused) {
      // Deactivate is mutually exclusive with Activate. Setting kind=discard
      // also clears manually_activated so the two states can't coexist.
      update.mutate({
        boxId: focused.box_id,
        patch: { kind: "discard", manually_activated: false },
      });
    }
  }

  function handleActivate() {
    if (focused) {
      // Activate is mutually exclusive with Deactivate. If the box was
      // previously discarded, restore kind to "paragraph" (a safe default;
      // user can re-categorize via the kind dropdown). Then mark manually
      // activated so it's included regardless of confidence threshold.
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
        <button className="mt-4 bg-blue-600 text-white px-3 py-1 rounded" onClick={runSegment} disabled={running}>
          {running ? "Segmenting…" : "Run segmentation"}
        </button>
        <StageIndicator state={streamState} />
      </div>
    );
  }

  const extractEnabled = (segments.data.boxes ?? []).some((b) => b.kind !== "discard");

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white text-sm border-b border-navy-700 flex-shrink-0">
        {/* Spacer */}
        <div className="flex-1" />

        {/* RIGHT: Alle Seiten extrahieren */}
        <button
          aria-label="Alle Seiten extrahieren"
          className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded disabled:bg-gray-500 disabled:cursor-not-allowed"
          disabled={!extractEnabled || running}
          onClick={onRunExtractAll}
        >
          {running ? "Running…" : "Alle Seiten extrahieren"}
        </button>
      </div>

      {/* ── Content row ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Scrollable PDF canvas area — centered horizontally */}
        <div className="flex-1 overflow-auto p-4 relative">
          {/* Floating colour legend, top-left of the PDF pane */}
          <BoxLegend />
          {/* Floating zoom control, top-right of the PDF pane */}
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

        {/* Sidebar */}
        <PropertiesSidebar
          selected={focused}
          pageBoxCount={boxesOnPage.length}
          currentPage={page}
          totalPages={totalPages}
          confidenceThreshold={confidenceThreshold}
          showDeactivated={showDeactivated}
          onConfidenceChange={setConfidenceThreshold}
          onShowDeactivatedChange={setShowDeactivated}
          onRunExtractThisPage={onRunExtractThisPage}
          onResetPage={handleResetPage}
          extractEnabled={extractEnabled}
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
        />
      </div>

      <StageIndicator state={streamState} />
    </div>
  );
}

export function Segment() {
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;
  return <SegmentRoute token={token} />;
}

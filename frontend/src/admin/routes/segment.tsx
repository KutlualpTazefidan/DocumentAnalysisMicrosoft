// frontend/src/admin/routes/segment.tsx
import { useMemo, useReducer, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";

import { BoxOverlay } from "../components/BoxOverlay";
import { Pagination } from "../components/Pagination";
import { PdfPage } from "../components/PdfPage";
import { PropertiesSidebar } from "../components/PropertiesSidebar";
import { StageIndicator } from "../components/StageIndicator";
import { useBoxHotkeys } from "../hooks/useBoxHotkeys";
import {
  useCreateBox,
  useDeleteBox,
  useMergeBoxes,
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

type ExtractScope = "this-page" | "all-pages";

export function SegmentRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState(1);
  const scale = 1.5;
  const segments = useSegments(slug ?? "", token);
  // Bbox coords are pixel-space at the rasterization DPI used for YOLO
  // inference. To overlay them on a PDF.js viewport rendered at `scale`
  // (where scale=1 means 72 DPI / native PDF units), multiply by
  // (scale * 72 / raster_dpi). Default raster_dpi=144 covers legacy files.
  const rasterDpi = segments.data?.raster_dpi ?? 144;
  const boxScale = (scale * 72) / rasterDpi;
  const update = useUpdateBox(slug ?? "", token);
  const merge = useMergeBoxes(slug ?? "", token);
  const split = useSplitBox(slug ?? "", token);
  const newBox = useCreateBox(slug ?? "", token);
  const del = useDeleteBox(slug ?? "", token);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);
  const { success, error } = useToast();

  // Top-bar state
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);
  const [showDeactivated, setShowDeactivated] = useState(false);
  const [extractScope, setExtractScope] = useState<ExtractScope>("this-page");

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

  // Active boxes pass the confidence threshold; deactivated ones don't.
  const activeBoxIds = useMemo(
    () => new Set(allBoxesOnPage.filter((b) => b.confidence >= confidenceThreshold).map((b) => b.box_id)),
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
    () => (segments.data?.boxes ?? []).find((b) => b.box_id === selected[0]) ?? null,
    [segments.data, selected],
  );

  function handleSelect(boxId: string, multi: boolean) {
    setSelected((prev) =>
      multi ? (prev.includes(boxId) ? prev.filter((p) => p !== boxId) : [...prev, boxId]) : [boxId],
    );
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

  async function onRunExtract() {
    setRunning(true);
    try {
      const pageArg = extractScope === "this-page" ? page : undefined;
      for await (const ev of streamExtract(slug!, token, pageArg)) {
        dispatch(ev);
        if (ev.type === "work-complete") success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") error(ev.reason);
      }
    } finally {
      setRunning(false);
    }
  }

  useBoxHotkeys({
    enabled: !!focused,
    setKind: (k: BoxKind) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } }),
    merge: () => selected.length >= 2 && merge.mutate(selected),
    split: () => focused && split.mutate({ boxId: focused.box_id, splitY: (focused.bbox[1] + focused.bbox[3]) / 2 }),
    newBox: () => newBox.mutate({ page, bbox: [50, 50, 200, 200], kind: "paragraph" }),
    del: () => focused && del.mutate(focused.box_id),
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
    <div className="flex flex-col h-screen">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-4 py-2 bg-navy-800 text-white text-sm border-b border-navy-700 flex-shrink-0 flex-wrap">
        {/* Pagination */}
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="w-px h-5 bg-navy-600" />

        {/* Confidence threshold */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-300 whitespace-nowrap">
            Conf ≥ {confidenceThreshold.toFixed(2)}
          </label>
          <input
            aria-label="Confidence threshold"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidenceThreshold}
            onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
            className="w-24 accent-blue-400"
          />
        </div>

        {/* Show deactivated */}
        <label className="flex items-center gap-1 text-xs text-gray-300 cursor-pointer">
          <input
            aria-label="Show deactivated"
            type="checkbox"
            checked={showDeactivated}
            onChange={(e) => setShowDeactivated(e.target.checked)}
            className="accent-blue-400"
          />
          Show deactivated
        </label>

        <div className="w-px h-5 bg-navy-600" />

        {/* Extract scope + button */}
        <div className="flex items-center gap-2">
          <select
            aria-label="Extract scope"
            value={extractScope}
            onChange={(e) => setExtractScope(e.target.value as ExtractScope)}
            className="text-xs bg-navy-700 text-white border border-navy-600 rounded px-1 py-0.5"
          >
            <option value="this-page">Diese Seite</option>
            <option value="all-pages">Alle Seiten</option>
          </select>
          <button
            aria-label="Run extraction"
            className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-3 py-1 rounded disabled:bg-gray-500 disabled:cursor-not-allowed"
            disabled={!extractEnabled || running}
            onClick={onRunExtract}
          >
            {running ? "Running…" : "Run extraction"}
          </button>
        </div>
      </div>

      {/* ── Content row ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Scrollable PDF canvas area */}
        <div className="flex-1 overflow-auto p-4">
          <PdfPage slug={slug!} token={token} page={page} scale={scale}>
            {visibleBoxes.map((b) => (
              <BoxOverlay
                key={b.box_id}
                box={b}
                selected={selected.includes(b.box_id)}
                deactivated={!activeBoxIds.has(b.box_id)}
                onSelect={handleSelect}
                onChange={(boxId, bbox) => update.mutate({ boxId, patch: { bbox } })}
                scale={boxScale}
              />
            ))}
          </PdfPage>
        </div>

        {/* Sidebar */}
        <PropertiesSidebar
          selected={focused}
          pageBoxCount={boxesOnPage.length}
          onChangeKind={(k) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } })}
          onMerge={() => selected.length >= 2 && merge.mutate(selected)}
          onDelete={() => focused && del.mutate(focused.box_id)}
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

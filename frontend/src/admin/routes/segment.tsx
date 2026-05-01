// frontend/src/local-pdf/routes/segment.tsx
import { useMemo, useReducer, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useToast } from "../../shared/components/useToast";

import { BoxOverlay } from "../components/BoxOverlay";
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
import { streamSegment } from "../hooks/useExtract";
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
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const scale = 1.5;
  const segments = useSegments(slug ?? "", token);
  const update = useUpdateBox(slug ?? "", token);
  const merge = useMergeBoxes(slug ?? "", token);
  const split = useSplitBox(slug ?? "", token);
  const newBox = useCreateBox(slug ?? "", token);
  const del = useDeleteBox(slug ?? "", token);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);
  const { success, error } = useToast();

  const boxesOnPage = useMemo(
    () => (segments.data?.boxes ?? []).filter((b) => b.page === page),
    [segments.data, page],
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

  return (
    <div className="flex h-full relative">
      <main className="flex-1 overflow-auto p-4">
        <div className="flex gap-2 mb-2">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((p) => (
            <button key={p} className={`px-2 py-1 text-xs ${p === page ? "bg-gray-200" : ""}`} onClick={() => setPage(p)}>
              p{p}
            </button>
          ))}
        </div>
        <PdfPage slug={slug!} token={token} page={page} scale={scale}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={selected.includes(b.box_id)}
              onSelect={handleSelect}
              onChange={(boxId, bbox) => update.mutate({ boxId, patch: { bbox } })}
              scale={scale}
            />
          ))}
        </PdfPage>
      </main>
      <PropertiesSidebar
        selected={focused}
        pageBoxCount={boxesOnPage.length}
        onChangeKind={(k) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } })}
        onMerge={() => selected.length >= 2 && merge.mutate(selected)}
        onDelete={() => focused && del.mutate(focused.box_id)}
        onRunExtract={() => navigate(`/local-pdf/doc/${slug}/extract`)}
        extractEnabled={(segments.data.boxes ?? []).some((b) => b.kind !== "discard")}
      />
      <StageIndicator state={streamState} />
    </div>
  );
}

export function Segment() {
  return <div className="p-6">coming soon</div>;
}

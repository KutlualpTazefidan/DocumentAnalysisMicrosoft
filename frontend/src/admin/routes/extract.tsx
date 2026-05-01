// frontend/src/local-pdf/routes/extract.tsx
import { useEffect, useReducer, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";

import { BoxOverlay } from "../components/BoxOverlay";
import { HtmlEditor } from "../components/HtmlEditor";
import { PdfPage } from "../components/PdfPage";
import { StageIndicator } from "../components/StageIndicator";
import { useSegments } from "../hooks/useSegments";
import { streamExtract, useExportSourceElements, useExtractRegion, useHtml, usePutHtml } from "../hooks/useExtract";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import type { WorkerEvent } from "../types/domain";

interface Props {
  token: string;
}

function reducer(state: StreamState, ev: WorkerEvent): StreamState {
  return applyEvent(state, ev);
}

export function ExtractRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const segments = useSegments(slug ?? "", token);
  const html = useHtml(slug ?? "", token);
  const putHtml = usePutHtml(slug ?? "", token);
  const exportSrc = useExportSourceElements(slug ?? "", token);
  const extractRegion = useExtractRegion(slug ?? "", token);
  const [page, setPage] = useState(1);
  const [running, setRunning] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);

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
        if (ev.type === "work-complete") toast.success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") toast.error(ev.reason);
      }
      await html.refetch();
    } finally {
      setRunning(false);
    }
  }

  function handleExport() {
    exportSrc.mutate(undefined, {
      onSuccess: () => toast.success("Exported sourceelements.json"),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  function handleClickElement(boxId: string) {
    setHighlight(boxId);
    const target = (segments.data?.boxes ?? []).find((b) => b.box_id === boxId);
    if (target) setPage(target.page);
  }

  function handleRegion(boxId: string) {
    extractRegion.mutate(boxId, {
      onSuccess: (r) => toast.success(`re-extracted ${r.box_id}`),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  const boxesOnPage = (segments.data?.boxes ?? []).filter((b) => b.page === page);

  if (!html.data) {
    return (
      <div className="p-6 relative">
        <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={runExtract} disabled={running}>
          {running ? "Extracting…" : "Run extraction"}
        </button>
        <StageIndicator state={streamState} />
      </div>
    );
  }

  return (
    <div className="flex h-full relative">
      <section className="w-1/2 overflow-auto p-2 border-r">
        <PdfPage slug={slug!} token={token} page={page} scale={1.2}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={highlight === b.box_id}
              onSelect={(id) => handleRegion(id)}
              onChange={() => {}}
              scale={1.2}
            />
          ))}
        </PdfPage>
      </section>
      <section className="w-1/2 flex flex-col">
        <div className="flex justify-end p-2 border-b gap-2">
          <button className="text-sm px-3 py-1 bg-blue-600 text-white rounded" disabled={exportSrc.isPending} onClick={handleExport}>
            Export →
          </button>
        </div>
        <HtmlEditor html={html.data} onChange={handleHtmlChange} onClickElement={handleClickElement} />
      </section>
      <StageIndicator state={streamState} />
    </div>
  );
}

export function Extract() {
  return <div className="p-6">coming soon</div>;
}

// frontend/src/local-pdf/hooks/usePdfPage.ts
import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist/build/pdf.mjs";

GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.mjs", import.meta.url).toString();

export interface PageState {
  numPages: number;
  viewport: { width: number; height: number };
  canvasRef: React.RefObject<HTMLCanvasElement>;
  loading: boolean;
  error: string | null;
}

export function usePdfPage(url: string, token: string, page: number, scale: number): PageState {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Track the in-flight render task so we can abort it when the user changes
  // page/scale rapidly. Without this, PDF.js throws "Cannot use the same
  // canvas during multiple render() operations".
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Abort any in-flight render before starting a new one.
    if (renderTaskRef.current) {
      try { renderTaskRef.current.cancel(); } catch { /* ignored */ }
      renderTaskRef.current = null;
    }
    (async () => {
      try {
        const task = getDocument({ url, httpHeaders: { "X-Auth-Token": token }, withCredentials: false });
        const pdf = await task.promise;
        if (cancelled) return;
        setNumPages(pdf.numPages);
        const p = await pdf.getPage(page);
        if (cancelled) return;
        const vp = p.getViewport({ scale });
        setViewport({ width: vp.width, height: vp.height });
        if (canvasRef.current) {
          const canvas = canvasRef.current;
          canvas.width = vp.width;
          canvas.height = vp.height;
          // pdfjs-dist's RenderTask has both `promise` and `cancel()`; the
          // bundled types only expose `promise`, so we cast.
          const renderTask = p.render({ canvasContext: canvas.getContext("2d")!, viewport: vp }) as unknown as { promise: Promise<void>; cancel: () => void };
          renderTaskRef.current = renderTask;
          try {
            await renderTask.promise;
          } catch (e: unknown) {
            // RenderingCancelledException is the expected outcome when the
            // user keeps zooming — silently swallow it.
            const name = (e as { name?: string } | null)?.name;
            if (name !== "RenderingCancelledException") throw e;
          } finally {
            if (renderTaskRef.current === renderTask) renderTaskRef.current = null;
          }
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (renderTaskRef.current) {
        try { renderTaskRef.current.cancel(); } catch { /* ignored */ }
        renderTaskRef.current = null;
      }
    };
  }, [url, token, page, scale]);

  return { numPages, viewport, canvasRef, loading, error };
}

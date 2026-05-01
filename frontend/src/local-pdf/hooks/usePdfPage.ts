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
  const [numPages, setNumPages] = useState(0);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const task = getDocument({ url, httpHeaders: { "X-Auth-Token": token }, withCredentials: false });
        const pdf = await task.promise;
        if (cancelled) return;
        setNumPages(pdf.numPages);
        const p = await pdf.getPage(page);
        const vp = p.getViewport({ scale });
        setViewport({ width: vp.width, height: vp.height });
        if (canvasRef.current) {
          const canvas = canvasRef.current;
          canvas.width = vp.width;
          canvas.height = vp.height;
          await p.render({ canvasContext: canvas.getContext("2d")!, viewport: vp }).promise;
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url, token, page, scale]);

  return { numPages, viewport, canvasRef, loading, error };
}

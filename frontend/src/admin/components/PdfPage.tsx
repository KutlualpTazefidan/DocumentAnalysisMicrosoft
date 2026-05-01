// frontend/src/local-pdf/components/PdfPage.tsx
import { usePdfPage } from "../hooks/usePdfPage";
import { apiBase } from "../api/adminClient";

interface Props {
  slug: string;
  token: string;
  page: number;
  scale: number;
  children?: React.ReactNode;
}

export function PdfPage({ slug, token, page, scale, children }: Props): JSX.Element {
  const url = `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/source.pdf`;
  const { canvasRef, viewport, loading, error } = usePdfPage(url, token, page, scale);
  if (error) return <div className="text-red-600 p-4">PDF error: {error}</div>;
  return (
    <div className="relative" style={{ width: viewport.width, height: viewport.height }}>
      <canvas ref={canvasRef} />
      {loading && <div className="absolute inset-0 bg-white/60 grid place-items-center">loading…</div>}
      {children}
    </div>
  );
}

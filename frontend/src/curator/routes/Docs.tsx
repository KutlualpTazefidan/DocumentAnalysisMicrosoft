import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { listAssignedDocs } from "../api/curatorClient";

export function CuratorDocs() {
  const { token } = useAuth();
  const q = useQuery({
    queryKey: ["curate", "docs"],
    queryFn: () => listAssignedDocs(token!),
    enabled: true,
  });
  if (q.isLoading) return <div className="p-6 h-full overflow-auto">Lade…</div>;
  if (q.isError) return <div className="p-6 text-bam-red">Fehler beim Laden.</div>;
  return (
    <div className="p-6 h-full overflow-auto">
      <h1 className="text-xl font-semibold mb-4 text-bam-navy">Meine zugewiesenen Dokumente</h1>
      <ul className="space-y-2">
        {(q.data ?? []).map((d) => (
          <li key={d.slug} className="card p-3 flex justify-between items-center">
            <div>
              <div className="font-medium">{d.filename}</div>
              <div className="text-xs text-ink-muted">{d.pages} Seiten</div>
            </div>
            <Link to={`/curate/doc/${d.slug}`} className="text-bam-cyan-700 hover:underline font-medium">öffnen</Link>
          </li>
        ))}
        {q.data?.length === 0 && <li className="text-ink-muted">Keine Dokumente zugewiesen.</li>}
      </ul>
    </div>
  );
}

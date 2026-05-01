import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { listAssignedDocs } from "../api/curatorClient";

export function CuratorDocs() {
  const { token } = useAuth();
  const q = useQuery({
    queryKey: ["curate", "docs"],
    queryFn: () => listAssignedDocs(token!),
    enabled: !!token,
  });
  if (q.isLoading) return <div className="p-6">Lade…</div>;
  if (q.isError) return <div className="p-6 text-red-600">Fehler beim Laden.</div>;
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Meine zugewiesenen Dokumente</h1>
      <ul className="space-y-2">
        {(q.data ?? []).map((d) => (
          <li key={d.slug} className="border rounded p-3 flex justify-between items-center">
            <div>
              <div className="font-medium">{d.filename}</div>
              <div className="text-xs text-slate-500">{d.pages} Seiten</div>
            </div>
            <Link to={`/curate/doc/${d.slug}`} className="text-blue-600 underline">öffnen</Link>
          </li>
        ))}
        {q.data?.length === 0 && <li className="text-slate-500">Keine Dokumente zugewiesen.</li>}
      </ul>
    </div>
  );
}

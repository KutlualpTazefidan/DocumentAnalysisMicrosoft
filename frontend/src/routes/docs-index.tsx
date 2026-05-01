import { Link } from "react-router-dom";
import { useDocs } from "../curator/hooks/useDocs";
import { Spinner } from "../shared/components/Spinner";

export function DocsIndex() {
  const { data, isLoading, error } = useDocs();

  if (isLoading) {
    return (
      <main className="p-8">
        <Spinner label="Lade Dokumente…" />
      </main>
    );
  }
  if (error) {
    return (
      <main className="p-8">
        <p role="alert" className="text-red-600">
          Fehler beim Laden der Dokumente.
        </p>
      </main>
    );
  }
  if (!data || data.length === 0) {
    return (
      <main className="p-8">
        <p>Keine Dokumente unter <code>outputs/</code>. Lege eines an und reload.</p>
      </main>
    );
  }
  return (
    <main className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Dokumente</h1>
      <ul className="space-y-2">
        {data.map((doc) => (
          <li key={doc.slug}>
            <Link
              to={`/docs/${encodeURIComponent(doc.slug)}/elements`}
              className="block bg-white border border-slate-200 rounded p-4 hover:border-blue-500 transition"
            >
              <span className="font-medium">{doc.slug}</span>
              <span className="ml-3 text-sm text-slate-500">
                {doc.element_count} elements
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

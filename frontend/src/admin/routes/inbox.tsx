// frontend/src/admin/routes/inbox.tsx
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { Plus, Trash2 } from "../../shared/icons";

import { useDeleteDoc, useDocs, usePublishDoc, useUploadDoc } from "../hooks/useDocs";
import { DocStatusBadge } from "../components/StatusBadge";
import { DocStepTabs } from "../components/DocStepTabs";
import { T } from "../styles/typography";

interface Props {
  token: string;
}

export function InboxRoute({ token }: Props): JSX.Element {
  const docs = useDocs(token);
  const upload = useUploadDoc(token);
  const publish = usePublishDoc(token);
  const del = useDeleteDoc(token);
  const fileRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("");
  const { success, error } = useToast();

  function handlePickFile() {
    fileRef.current?.click();
  }

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate(f, {
      onSuccess: (m) => success(`${m.slug} hochgeladen`),
      onError: (err) => error(`Upload fehlgeschlagen: ${(err as Error).message}`),
    });
    e.target.value = "";
  }

  const rows = (docs.data ?? []).filter((d) => d.filename.toLowerCase().includes(filter.toLowerCase()) || d.slug.includes(filter.toLowerCase()));

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 bg-chrome2 text-white flex-shrink-0">
        <DocStepTabs />
      </div>
      <div className="p-6 flex-1 overflow-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className={T.cardTitle}>Dokumente</h1>
        <input
          type="text"
          className="input ml-auto max-w-xs"
          placeholder="suchen…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button className="btn-primary flex items-center gap-1" onClick={handlePickFile}>
          <Plus className="w-4 h-4" /> PDF hinzufügen
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={handleFile} />
      </div>
      <table className={`w-full ${T.body}`}>
        <thead>
          <tr className="text-left border-b">
            <th className="p-2">Dateiname</th>
            <th className="p-2">Seiten</th>
            <th className="p-2">Status</th>
            <th className="p-2">Elemente</th>
            <th className="p-2">Zuletzt geändert</th>
            <th className="p-2">Aktion</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.slug} className="border-b">
              <td className="p-2">{d.filename}</td>
              <td className="p-2">{d.pages}</td>
              <td className="p-2">
                <DocStatusBadge status={d.status} />
              </td>
              <td className="p-2">{d.box_count}</td>
              <td className={`p-2 ${T.body} text-gray-500`}>{d.last_touched_utc}</td>
              <td className="p-2 flex items-center gap-2">
                <Link className="text-blue-600 underline" to={`/admin/doc/${d.slug}/extract`}>
                  {d.status === "raw" ? "starten" : d.status === "done" ? "ansehen" : "fortsetzen"}
                </Link>
                {(d.status === "extracted" || d.status === "synthesised") && (
                  <button
                    className={`${T.body} bg-green-600 text-white px-2 py-0.5 rounded`}
                    onClick={() => publish.mutate(d.slug, {
                      onSuccess: () => success(`${d.slug} veröffentlicht`),
                      onError: (err) => error(`Veröffentlichen fehlgeschlagen: ${(err as Error).message}`),
                    })}
                  >
                    Veröffentlichen
                  </button>
                )}
                <button
                  aria-label={`${d.slug} löschen`}
                  title="Dokument und alle erzeugten Dateien löschen"
                  className={`${T.body} ml-auto p-1 text-slate-400 hover:text-red-600 disabled:opacity-40`}
                  disabled={del.isPending}
                  onClick={() => {
                    if (!window.confirm(`Wirklich „${d.filename}" und alle erzeugten Dateien löschen? Das kann nicht rückgängig gemacht werden.`)) return;
                    del.mutate(d.slug, {
                      onSuccess: () => success(`gelöscht: ${d.slug}`),
                      onError: (err) => error(`Löschen fehlgeschlagen: ${(err as Error).message}`),
                    });
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={`${T.body} text-gray-400 mt-4`}>PDFs auf dem Server unter <code>data/raw-pdfs/</code> ablegen oder „PDF hinzufügen" oben rechts nutzen.</p>
    </div>
    </div>
  );
}

export function Inbox() {
  const { token } = useAuth();
  if (token === null) return <div className="p-6 h-full overflow-auto">Nicht angemeldet.</div>;
  return <InboxRoute token={token} />;
}

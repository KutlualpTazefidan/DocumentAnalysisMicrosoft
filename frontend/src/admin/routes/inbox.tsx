// frontend/src/admin/routes/inbox.tsx
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { Plus, Trash2 } from "../../shared/icons";

import { useDeleteDoc, useDocs, usePublishDoc, useUploadDoc } from "../hooks/useDocs";
import { StatusBadge } from "../components/StatusBadge";
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
      onSuccess: (m) => success(`uploaded ${m.slug}`),
      onError: (err) => error(`upload failed: ${(err as Error).message}`),
    });
    e.target.value = "";
  }

  const rows = (docs.data ?? []).filter((d) => d.filename.toLowerCase().includes(filter.toLowerCase()) || d.slug.includes(filter.toLowerCase()));

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-navy-800 text-white border-b border-navy-700 flex-shrink-0">
        <DocStepTabs />
      </div>
      <div className="p-6 flex-1 overflow-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className={T.cardTitle}>Local-PDF Inbox</h1>
        <input
          type="text"
          className={`ml-auto border rounded px-2 py-1 ${T.body}`}
          placeholder="search…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button className={`flex items-center gap-1 bg-blue-600 text-white px-3 py-1 rounded ${T.body}`} onClick={handlePickFile}>
          <Plus className="w-4 h-4" /> Add PDF
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={handleFile} />
      </div>
      <table className={`w-full ${T.body}`}>
        <thead>
          <tr className="text-left border-b">
            <th className="p-2">filename</th>
            <th className="p-2">pages</th>
            <th className="p-2">status</th>
            <th className="p-2">boxes</th>
            <th className="p-2">last touched</th>
            <th className="p-2">action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.slug} className="border-b">
              <td className="p-2">{d.filename}</td>
              <td className="p-2">{d.pages}</td>
              <td className="p-2">
                <StatusBadge status={d.status} />
              </td>
              <td className="p-2">{d.box_count}</td>
              <td className={`p-2 ${T.body} text-gray-500`}>{d.last_touched_utc}</td>
              <td className="p-2 flex items-center gap-2">
                <Link className="text-blue-600 underline" to={`/admin/doc/${d.slug}/extract`}>
                  {d.status === "raw" ? "start" : d.status === "done" ? "view" : "resume"}
                </Link>
                {(d.status === "extracted" || d.status === "synthesised") && (
                  <button
                    className={`${T.body} bg-green-600 text-white px-2 py-0.5 rounded`}
                    onClick={() => publish.mutate(d.slug, {
                      onSuccess: () => success(`published ${d.slug}`),
                      onError: (err) => error(`publish failed: ${(err as Error).message}`),
                    })}
                  >
                    Publish
                  </button>
                )}
                <button
                  aria-label={`Delete ${d.slug}`}
                  title="Delete this doc and all its files"
                  className={`${T.body} ml-auto p-1 text-slate-400 hover:text-red-600 disabled:opacity-40`}
                  disabled={del.isPending}
                  onClick={() => {
                    if (!window.confirm(`Wirklich „${d.filename}" und alle erzeugten Dateien löschen? Das kann nicht rückgängig gemacht werden.`)) return;
                    del.mutate(d.slug, {
                      onSuccess: () => success(`gelöscht: ${d.slug}`),
                      onError: (err) => error(`delete failed: ${(err as Error).message}`),
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
      <p className={`${T.body} text-gray-400 mt-4`}>Drop PDFs into <code>data/raw-pdfs/</code> or use Add PDF.</p>
    </div>
    </div>
  );
}

export function Inbox() {
  const { token } = useAuth();
  if (!token) return <div className="p-6 h-full overflow-auto">Not authorised.</div>;
  return <InboxRoute token={token} />;
}

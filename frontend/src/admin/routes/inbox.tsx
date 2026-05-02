// frontend/src/admin/routes/inbox.tsx
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useToast } from "../../shared/components/useToast";
import { Plus } from "../../shared/icons";

import { useDocs, usePublishDoc, useUploadDoc } from "../hooks/useDocs";
import { StatusBadge } from "../components/StatusBadge";
import { DocStepTabs } from "../components/DocStepTabs";

interface Props {
  token: string;
}

export function InboxRoute({ token }: Props): JSX.Element {
  const docs = useDocs(token);
  const upload = useUploadDoc(token);
  const publish = usePublishDoc(token);
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
      <div className="flex items-center justify-between px-4 py-2 bg-navy-800 text-white text-xs border-b border-navy-700 flex-shrink-0">
        <DocStepTabs />
      </div>
      <div className="p-6 flex-1 overflow-auto">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold">Local-PDF Inbox</h1>
        <input
          type="text"
          className="ml-auto border rounded px-2 py-1 text-sm"
          placeholder="search…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button className="flex items-center gap-1 bg-blue-600 text-white px-3 py-1 rounded text-sm" onClick={handlePickFile}>
          <Plus className="w-4 h-4" /> Add PDF
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={handleFile} />
      </div>
      <table className="w-full text-sm">
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
              <td className="p-2 text-xs text-gray-500">{d.last_touched_utc}</td>
              <td className="p-2 flex items-center gap-2">
                <Link className="text-blue-600 underline" to={`/admin/doc/${d.slug}/segment`}>
                  {d.status === "raw" ? "start" : d.status === "done" ? "view" : "resume"}
                </Link>
                {(d.status === "extracted" || d.status === "synthesised") && (
                  <button
                    className="text-xs bg-green-600 text-white px-2 py-0.5 rounded"
                    onClick={() => publish.mutate(d.slug, {
                      onSuccess: () => success(`published ${d.slug}`),
                      onError: (err) => error(`publish failed: ${(err as Error).message}`),
                    })}
                  >
                    Publish
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-400 mt-4">Drop PDFs into <code>data/raw-pdfs/</code> or use Add PDF.</p>
    </div>
    </div>
  );
}

export function Inbox() {
  const { token } = useAuth();
  if (!token) return <div className="p-6 h-full overflow-auto">Not authorised.</div>;
  return <InboxRoute token={token} />;
}

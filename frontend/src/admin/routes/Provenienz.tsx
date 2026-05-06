import { useState } from "react";
import { useParams } from "react-router-dom";
import { GitMerge, Plus, Trash2 } from "lucide-react";
import { ReactFlowProvider } from "reactflow";

import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";
import { Canvas } from "../provenienz/Canvas";
import { SidePanel } from "../provenienz/SidePanel";
import {
  useCreateSession,
  useDeleteSession,
  useSession,
  useSessions,
  type SessionMeta,
} from "../hooks/useProvenienz";
import { T } from "../styles/typography";

export function Provenienz(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const tokenStr = token ?? "";

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [rootChunkInput, setRootChunkInput] = useState("");

  const { data: sessions, isLoading, error } = useSessions(slug, tokenStr);
  const create = useCreateSession(tokenStr);
  const del = useDeleteSession(tokenStr, slug);
  const detail = useSession(selectedId, tokenStr);

  if (!token) {
    return <div className="p-6 text-slate-300">Bitte zuerst anmelden.</div>;
  }

  async function handleCreate() {
    if (!rootChunkInput.trim()) return;
    const m = await create.mutateAsync({
      slug,
      root_chunk_id: rootChunkInput.trim(),
    });
    setSelectedId(m.session_id);
    setRootChunkInput("");
    setCreating(false);
  }

  async function handleDelete(sessionId: string) {
    if (!window.confirm("Sitzung wirklich löschen?")) return;
    await del.mutateAsync(sessionId);
    if (selectedId === sessionId) {
      setSelectedId(null);
      setSelectedNodeId(null);
    }
  }

  return (
    <div className="flex flex-col h-full bg-navy-900">
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700">
        <DocStepTabs slug={slug} />
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Left rail */}
        <aside className="w-72 shrink-0 border-r border-navy-700 bg-navy-800/50 overflow-y-auto">
          <div className="flex items-center justify-between px-3 py-3 border-b border-navy-700">
            <h2 className={`${T.heading} text-white flex items-center gap-2`}>
              <GitMerge className="w-4 h-4" aria-hidden /> Sitzungen
            </h2>
            <button
              type="button"
              onClick={() => setCreating(true)}
              className={`text-blue-400 hover:text-blue-300 ${T.body} flex items-center gap-1`}
            >
              <Plus className="w-4 h-4" aria-hidden /> Neu
            </button>
          </div>

          {creating && (
            <div className="p-3 border-b border-navy-700 space-y-2">
              <label className={`${T.body} text-slate-300 block`}>
                Wurzel-Chunk (z.B. p1-b0)
              </label>
              <input
                type="text"
                value={rootChunkInput}
                onChange={(e) => setRootChunkInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCreate();
                  if (e.key === "Escape") setCreating(false);
                }}
                className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
                autoFocus
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={!rootChunkInput.trim() || create.isPending}
                  className={`px-2 py-1 rounded bg-blue-500 text-white ${T.tiny} disabled:opacity-50`}
                >
                  {create.isPending ? "..." : "Anlegen"}
                </button>
                <button
                  type="button"
                  onClick={() => setCreating(false)}
                  className={`px-2 py-1 rounded text-slate-300 ${T.tiny} hover:bg-navy-700`}
                >
                  Abbrechen
                </button>
              </div>
              {create.error && (
                <p className={`text-red-400 ${T.tiny}`}>{create.error.message}</p>
              )}
            </div>
          )}

          {isLoading && (
            <p className={`px-3 py-2 text-slate-400 ${T.body}`}>Lade...</p>
          )}
          {error && (
            <p className={`px-3 py-2 text-red-400 ${T.body}`}>{error.message}</p>
          )}
          {sessions && sessions.length === 0 && !isLoading && (
            <p className={`px-3 py-2 text-slate-500 ${T.body} italic`}>
              Keine Sitzungen für dieses Dokument.
            </p>
          )}
          <ul className="divide-y divide-navy-700">
            {sessions?.map((s) => (
              <li
                key={s.session_id}
                className={`px-3 py-2 cursor-pointer hover:bg-navy-700/40 ${
                  selectedId === s.session_id ? "bg-navy-700/60" : ""
                }`}
                onClick={() => {
                  setSelectedId(s.session_id);
                  setSelectedNodeId(null);
                }}
              >
                <SessionRow
                  session={s}
                  onDelete={() => void handleDelete(s.session_id)}
                />
              </li>
            ))}
          </ul>
        </aside>

        {/* Right area */}
        <main className="flex-1 min-w-0 flex flex-col text-slate-200">
          {!selectedId && (
            <p className={`${T.body} text-slate-400 italic p-4`}>
              Sitzung links auswählen oder neu anlegen.
            </p>
          )}
          {selectedId && detail.isLoading && <p className="p-4">Lade Sitzung...</p>}
          {selectedId && detail.error && (
            <p className="p-4 text-red-400">{detail.error.message}</p>
          )}
          {selectedId && detail.data && (
            <>
              <header className="border-b border-navy-700 px-4 py-2">
                <h2 className={`${T.cardTitle} text-white`}>
                  Sitzung {detail.data.meta.session_id}
                </h2>
                <p className={`text-slate-400 ${T.body}`}>
                  Wurzel-Chunk: {detail.data.meta.root_chunk_id} · Status:{" "}
                  {detail.data.meta.status} · {detail.data.nodes.length} Knoten ·{" "}
                  {detail.data.edges.length} Kanten
                </p>
              </header>
              <div className="flex-1 min-h-0 flex">
                <div className="flex-1 min-w-0">
                  <ReactFlowProvider>
                    <Canvas
                      nodes={detail.data.nodes}
                      edges={detail.data.edges}
                      onSelectNode={setSelectedNodeId}
                    />
                  </ReactFlowProvider>
                </div>
                <aside className="w-80 shrink-0 border-l border-navy-700 bg-navy-800/40 overflow-y-auto">
                  <SidePanel
                    sessionId={detail.data.meta.session_id}
                    token={tokenStr}
                    selectedNodeId={selectedNodeId}
                    nodes={detail.data.nodes}
                    edges={detail.data.edges}
                    onSelectNode={setSelectedNodeId}
                  />
                </aside>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function SessionRow({
  session,
  onDelete,
}: {
  session: SessionMeta;
  onDelete: () => void;
}): JSX.Element {
  const status = session.status === "closed" ? "🔒" : "🔓";
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className={`text-white ${T.mono} truncate`}>
          {status} {session.session_id.slice(0, 12)}…
        </p>
        <p className={`text-slate-400 ${T.tiny} truncate`}>
          Wurzel: {session.root_chunk_id}
        </p>
        <p className="text-slate-500 text-[10px]">{session.last_touched_at}</p>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="text-red-400/70 hover:text-red-300"
        aria-label="Sitzung löschen"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}


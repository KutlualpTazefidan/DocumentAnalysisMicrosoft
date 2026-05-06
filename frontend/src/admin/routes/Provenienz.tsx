import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import { Bot, FolderTree, GitMerge, Plus, Trash2 } from "lucide-react";
import { ReactFlowProvider } from "reactflow";

import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";
import { AgentCanvas } from "../provenienz/AgentCanvas";
import { AgentInspector } from "../provenienz/AgentInspector";
import { ApproachLibrary } from "../provenienz/ApproachLibrary";
import { ToolRegistry } from "../provenienz/ToolRegistry";
import { Canvas } from "../provenienz/Canvas";
import { ChunkPicker } from "../provenienz/ChunkPicker";
import { SidePanel } from "../provenienz/SidePanel";
import {
  useAgentInfo,
  useCreateSession,
  useDeleteSession,
  useSession,
  useSessions,
  type SessionMeta,
} from "../hooks/useProvenienz";
import type { ViewNode } from "../provenienz/layout";
import { T } from "../styles/typography";

type View = "sessions" | "agent";

export function Provenienz(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const tokenStr = token ?? "";

  const [view, setView] = useState<View>("sessions");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedViewId, setSelectedViewId] = useState<string | null>(null);
  const [viewIndex, setViewIndex] = useState<Map<string, ViewNode>>(
    () => new Map(),
  );
  const [creating, setCreating] = useState(false);
  const [agentSelectedId, setAgentSelectedId] = useState<string | null>(null);
  const agentInfo = useAgentInfo(tokenStr);

  const handleViewIndex = useCallback((idx: Map<string, ViewNode>) => {
    setViewIndex(idx);
  }, []);

  const { data: sessions, isLoading, error } = useSessions(slug, tokenStr);
  const create = useCreateSession(tokenStr);
  const del = useDeleteSession(tokenStr, slug);
  const detail = useSession(selectedId, tokenStr);

  if (!token) {
    return <div className="p-6 text-slate-300">Bitte zuerst anmelden.</div>;
  }

  async function handlePickChunk(boxId: string) {
    const m = await create.mutateAsync({ slug, root_chunk_id: boxId });
    setSelectedId(m.session_id);
    setSelectedViewId(null);
    setCreating(false);
  }

  async function handleDelete(sessionId: string) {
    if (!window.confirm("Sitzung wirklich löschen?")) return;
    await del.mutateAsync(sessionId);
    if (selectedId === sessionId) {
      setSelectedId(null);
      setSelectedViewId(null);
    }
  }

  return (
    <div className="flex flex-col h-full bg-navy-900">
      <div className="flex items-center justify-between px-4 py-2 bg-navy-800 text-white border-b border-navy-700">
        <DocStepTabs slug={slug} />
        <ViewToggle view={view} onChange={setView} />
      </div>

      {view === "agent" ? (
        <AgentView
          agentInfo={agentInfo.data}
          isLoading={agentInfo.isLoading}
          error={agentInfo.error}
          token={tokenStr}
          selectedId={agentSelectedId}
          onSelect={setAgentSelectedId}
        />
      ) : (
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
                  setSelectedViewId(null);
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
          {creating && (
            <ChunkPicker
              slug={slug}
              token={tokenStr}
              onPick={(boxId) => void handlePickChunk(boxId)}
              onCancel={() => setCreating(false)}
              pending={create.isPending}
              errorMessage={create.error?.message}
            />
          )}
          {!creating && !selectedId && (
            <p className={`${T.body} text-slate-400 italic p-4`}>
              Sitzung links auswählen oder neu anlegen.
            </p>
          )}
          {!creating && selectedId && detail.isLoading && <p className="p-4">Lade Sitzung...</p>}
          {!creating && selectedId && detail.error && (
            <p className="p-4 text-red-400">{detail.error.message}</p>
          )}
          {!creating && selectedId && detail.data && (
            <>
              <SessionHeader detail={detail.data} token={tokenStr} />
              <div className="flex-1 min-h-0 flex">
                <div className="flex-1 min-w-0">
                  <ReactFlowProvider>
                    <Canvas
                      nodes={detail.data.nodes}
                      edges={detail.data.edges}
                      meta={detail.data.meta}
                      sessionId={detail.data.meta.session_id}
                      onSelectView={setSelectedViewId}
                      onViewIndex={handleViewIndex}
                    />
                  </ReactFlowProvider>
                </div>
                <aside className="w-80 shrink-0 border-l border-navy-700 bg-navy-800/40 overflow-y-auto">
                  <SidePanel
                    sessionId={detail.data.meta.session_id}
                    token={tokenStr}
                    selectedViewId={selectedViewId}
                    viewIndex={viewIndex}
                    nodes={detail.data.nodes}
                    edges={detail.data.edges}
                    onSelectView={setSelectedViewId}
                  />
                </aside>
              </div>
            </>
          )}
        </main>
      </div>
      )}
    </div>
  );
}

function ViewToggle({
  view,
  onChange,
}: {
  view: View;
  onChange: (v: View) => void;
}): JSX.Element {
  const item = (key: View, label: string, Icon: typeof FolderTree): JSX.Element => {
    const active = key === view;
    return (
      <button
        type="button"
        onClick={() => onChange(key)}
        className={`px-3 py-1 rounded flex items-center gap-1.5 ${T.body} transition-colors ${
          active
            ? "bg-blue-600 text-white"
            : "text-slate-300 hover:bg-navy-700"
        }`}
      >
        <Icon className="w-4 h-4" aria-hidden />
        {label}
      </button>
    );
  };
  return (
    <nav className="flex items-center gap-1 bg-navy-900/60 border border-navy-600 rounded p-0.5">
      {item("sessions", "Sitzungen", FolderTree)}
      {item("agent", "Agent", Bot)}
    </nav>
  );
}

function AgentView({
  agentInfo,
  isLoading,
  error,
  token,
  selectedId,
  onSelect,
}: {
  agentInfo: ReturnType<typeof useAgentInfo>["data"];
  isLoading: boolean;
  error: Error | null;
  token: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}): JSX.Element {
  if (isLoading) {
    return <p className={`p-6 text-slate-400 ${T.body}`}>Lade Agent-Topologie…</p>;
  }
  if (error) {
    return <p className={`p-6 text-red-400 ${T.body}`}>{error.message}</p>;
  }
  if (!agentInfo) return <></>;
  return (
    <div className="flex flex-1 min-h-0">
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="px-4 py-3 border-b border-navy-700">
          <p className={`${T.tinyBold}`}>Modell aktiv</p>
          <p className="text-white">
            <code className="text-amber-300">{agentInfo.llm.backend}</code>
            {" · "}
            <code className="text-amber-300">{agentInfo.llm.model || "–"}</code>
          </p>
        </header>
        <div className="flex-1 min-h-0">
          <ReactFlowProvider>
            <AgentCanvas info={agentInfo} selectedId={selectedId} onSelect={onSelect} />
          </ReactFlowProvider>
        </div>
        <div className="border-t border-navy-700 max-h-[45%] overflow-y-auto p-4">
          <ToolRegistry tools={agentInfo.tools} onSelect={onSelect} />
          <ApproachLibrary token={token} />
        </div>
      </div>
      <aside className="w-80 shrink-0 border-l border-navy-700 bg-navy-800/40 overflow-y-auto">
        <AgentInspector
          info={agentInfo}
          selectedId={selectedId}
          onClose={() => onSelect(null)}
        />
      </aside>
    </div>
  );
}

function SessionHeader({
  detail,
}: {
  detail: { meta: SessionMeta; nodes: { kind: string }[]; edges: unknown[] };
  token: string;
}): JSX.Element {
  return (
    <header className="border-b border-navy-700 px-4 py-2">
      <h2 className={`${T.cardTitle} text-white`}>
        Sitzung {detail.meta.session_id}
      </h2>
      <p className={`text-slate-400 ${T.body}`}>
        Wurzel-Chunk: {detail.meta.root_chunk_id} · Status:{" "}
        {detail.meta.status} · {detail.nodes.length} Knoten ·{" "}
        {detail.edges.length} Kanten
      </p>
    </header>
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


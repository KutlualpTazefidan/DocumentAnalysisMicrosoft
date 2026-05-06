import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { ApproachFormModal, type ApproachFormValues } from "./ApproachFormModal";

import { useToast } from "../../shared/components/useToast";
import {
  useApproaches,
  useCreateApproach,
  useDeleteApproach,
  usePatchApproach,
  type Approach,
} from "../hooks/useProvenienz";
import { T } from "../styles/typography";

const STEP_KIND_OPTIONS = [
  "next_step",
  "extract_claims",
  "extract_goal",
  "formulate_task",
  "evaluate",
  "propose_stop",
] as const;

interface Props {
  token: string;
}

/**
 * CRUD list for the explicit-guidance approach library. Each approach is
 * a named system-prompt overlay; sessions can pin one or more (via the
 * /sessions/{id}/pin-approach route — exposed in the session header
 * elsewhere). This view is the authoring surface.
 */
export function ApproachLibrary({ token }: Props): JSX.Element {
  const { data: approaches, isLoading, error } = useApproaches(token, { enabledOnly: false });
  const [creating, setCreating] = useState(false);
  const create = useCreateApproach(token);
  const { error: toastError } = useToast();

  async function handleCreate(values: ApproachFormValues): Promise<void> {
    try {
      await create.mutateAsync(values);
      setCreating(false);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="border border-navy-700 rounded-lg bg-navy-800/40 p-4">
      <header className="flex items-center justify-between mb-2">
        <div>
          <h3 className={`${T.heading} text-white`}>Approach-Bibliothek</h3>
          <p className={`${T.body} text-slate-400`}>
            Benannte Prompt-Erweiterungen — werden gepinnten Sitzungen in
            den System-Prompt eingehängt. Approaches mit step_kind{" "}
            <code className="text-amber-300">next_step</code> bringen dem
            Agent bei <em>wie er denken soll</em> (Kapselregeln,
            Tool-Auswahl, Eskalation).
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className={`px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} flex items-center gap-1 shrink-0`}
        >
          <Plus className="w-4 h-4" /> Neu
        </button>
      </header>

      <ApproachFormModal
        open={creating}
        mode="create"
        initialValues={{
          name: "",
          step_kinds: ["next_step"],
          extra_system: "",
        }}
        onSubmit={handleCreate}
        onClose={() => setCreating(false)}
        busy={create.isPending}
        errorMessage={create.error?.message}
      />

      {isLoading && <p className={`${T.body} text-slate-400 mt-3`}>Lade…</p>}
      {error && (
        <p className={`${T.body} text-red-400 mt-3`}>{error.message}</p>
      )}
      {approaches && approaches.length === 0 && !isLoading && (
        <p className={`${T.body} text-slate-500 italic mt-3`}>
          Noch keine Approaches definiert.
        </p>
      )}

      <ApproachGroups approaches={approaches ?? []} token={token} />
    </div>
  );
}

const STEP_KIND_GROUP_LABEL: Record<string, string> = {
  next_step: "🧠 Agent-Denkregeln (next_step)",
  extract_goal: "🎯 Ziel-Ableitung (extract_goal)",
  extract_claims: "📜 Aussagen extrahieren",
  formulate_task: "🔍 Aufgabe formulieren",
  evaluate: "⚖ Bewerten",
  propose_stop: "🛑 Stopp vorschlagen",
};

/** Group approaches by their primary (first) step_kind. Approaches with
 *  multiple step_kinds are placed under the first, with the rest shown
 *  as additional badges on the row. */
function ApproachGroups({
  approaches,
  token,
}: {
  approaches: Approach[];
  token: string;
}): JSX.Element {
  const groups = new Map<string, Approach[]>();
  for (const a of approaches) {
    const primary = a.step_kinds[0] ?? "(ohne Step)";
    if (!groups.has(primary)) groups.set(primary, []);
    groups.get(primary)!.push(a);
  }
  // Render in the canonical STEP_KIND_OPTIONS order, then any extras.
  const orderedKinds = [
    ...STEP_KIND_OPTIONS.filter((s) => groups.has(s)),
    ...[...groups.keys()].filter(
      (k) => !STEP_KIND_OPTIONS.includes(k as (typeof STEP_KIND_OPTIONS)[number]),
    ),
  ];
  if (orderedKinds.length === 0) return <></>;
  return (
    <div className="mt-3 space-y-3">
      {orderedKinds.map((kind) => (
        <ApproachGroup
          key={kind}
          stepKind={kind}
          approaches={groups.get(kind) ?? []}
          token={token}
        />
      ))}
    </div>
  );
}

function ApproachGroup({
  stepKind,
  approaches,
  token,
}: {
  stepKind: string;
  approaches: Approach[];
  token: string;
}): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);
  const enabledCount = approaches.filter((a) => a.enabled).length;
  const label = STEP_KIND_GROUP_LABEL[stepKind] ?? stepKind;
  return (
    <section className="rounded border border-navy-700 bg-navy-900/30">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-navy-800/40"
      >
        <div className="flex items-center gap-2 text-left">
          <span className={`${T.tinyBold} text-slate-200`}>
            {collapsed ? "▸" : "▾"} {label}
          </span>
          <span className={`${T.tiny} text-slate-400`}>
            {approaches.length} ({enabledCount} aktiv)
          </span>
        </div>
      </button>
      {!collapsed && (
        <ul className="px-3 pb-3 space-y-2">
          {approaches.map((a) => (
            <ApproachRow key={a.approach_id} approach={a} token={token} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ApproachRow({
  approach,
  token,
}: {
  approach: Approach;
  token: string;
}): JSX.Element {
  const [editOpen, setEditOpen] = useState(false);
  const patch = usePatchApproach(token);
  const del = useDeleteApproach(token);
  const { error: toastError } = useToast();

  async function handleToggle(): Promise<void> {
    try {
      await patch.mutateAsync({
        approachId: approach.approach_id,
        patch: { enabled: !approach.enabled },
      });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleEditSave(values: ApproachFormValues): Promise<void> {
    try {
      await patch.mutateAsync({
        approachId: approach.approach_id,
        patch: {
          extra_system: values.extra_system,
          step_kinds: values.step_kinds,
        },
      });
      setEditOpen(false);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (!window.confirm(`Approach "${approach.name}" löschen?`)) return;
    try {
      await del.mutateAsync(approach.approach_id);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <li
      className={`rounded border p-3 ${
        approach.enabled
          ? "border-navy-600 bg-navy-900/40"
          : "border-navy-700 bg-navy-900/20 opacity-60"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-white font-semibold">
            {approach.name}{" "}
            <span className={`${T.tiny} text-slate-400 font-normal`}>
              v{approach.version}
            </span>
          </p>
          <p className={`${T.tiny} text-slate-400`}>
            Schritte: {approach.step_kinds.join(", ")}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className={`px-2 py-0.5 rounded text-blue-300 hover:bg-blue-900/30 ${T.tiny} flex items-center gap-1`}
            aria-label="Bearbeiten"
            title="Im Vollbild bearbeiten"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit
          </button>
          <button
            type="button"
            onClick={() => void handleToggle()}
            disabled={patch.isPending}
            className={`px-2 py-0.5 rounded ${T.tiny} ${
              approach.enabled
                ? "bg-emerald-700 text-white hover:bg-emerald-600"
                : "bg-zinc-700 text-slate-300 hover:bg-zinc-600"
            }`}
          >
            {approach.enabled ? "aktiv" : "inaktiv"}
          </button>
          <button
            type="button"
            onClick={() => void handleDelete()}
            disabled={del.isPending}
            className="px-2 py-0.5 rounded text-red-400 hover:bg-red-900/30"
            aria-label="Löschen"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <pre
        onClick={() => setEditOpen(true)}
        className="mt-2 p-2 rounded bg-navy-950 text-slate-200 text-[11px] font-mono whitespace-pre-wrap break-words cursor-pointer hover:bg-navy-900 max-h-32 overflow-hidden"
        title="Klicken zum Bearbeiten"
      >
        {approach.extra_system}
      </pre>
      {patch.error && (
        <p className={`text-red-400 ${T.tiny} mt-1`}>{patch.error.message}</p>
      )}
      <ApproachFormModal
        open={editOpen}
        mode="edit"
        initialValues={{
          name: approach.name,
          step_kinds: approach.step_kinds,
          extra_system: approach.extra_system,
        }}
        versionPreview={`v${approach.version} → v${approach.version + 1} · ${approach.step_kinds.join(", ")}`}
        onSubmit={handleEditSave}
        onClose={() => setEditOpen(false)}
        busy={patch.isPending}
        errorMessage={patch.error?.message}
      />
    </li>
  );
}

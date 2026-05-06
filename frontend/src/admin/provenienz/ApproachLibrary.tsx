import { useState } from "react";
import { Maximize2, Plus, Trash2 } from "lucide-react";

import { FullscreenTextEditor } from "./FullscreenTextEditor";

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

const STEP_KIND_HINT: Record<string, string> = {
  next_step:
    "🧠 Beeinflusst, WIE der Agent den nächsten Schritt wählt — Heuristiken zu " +
    "Kapselregeln (capability_request vs. executable_step), Tool-Wahl, " +
    "Eskalations-Kriterien.",
  extract_goal:
    "Beeinflusst die automatische Ableitung des Sitzungs-Ziels aus Chunk + " +
    "erster Aussage.",
};

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
          onClick={() => setCreating((c) => !c)}
          className={`px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} flex items-center gap-1`}
        >
          <Plus className="w-4 h-4" /> {creating ? "Abbrechen" : "Neu"}
        </button>
      </header>

      {creating && <CreateForm token={token} onDone={() => setCreating(false)} />}

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

function CreateForm({ token, onDone }: { token: string; onDone: () => void }): JSX.Element {
  const [name, setName] = useState("");
  const [stepKinds, setStepKinds] = useState<string[]>(["extract_claims"]);
  const [showFullEditor, setShowFullEditor] = useState(false);
  const [text, setText] = useState("");
  const create = useCreateApproach(token);
  const { error: toastError } = useToast();

  async function handleSubmit(): Promise<void> {
    if (!name.trim() || stepKinds.length === 0 || !text.trim()) return;
    try {
      await create.mutateAsync({
        name: name.trim(),
        step_kinds: stepKinds,
        extra_system: text.trim(),
      });
      onDone();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="border border-navy-600 rounded p-3 mt-2 bg-navy-900/60 space-y-2">
      <div>
        <label className={`${T.tiny} text-slate-300 block`}>Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="z.B. thorough-numerics"
          className={`mt-0.5 w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
          autoFocus
        />
      </div>
      <div>
        <label className={`${T.tiny} text-slate-300 block`}>Anwendbar auf Schritte</label>
        <div className="flex flex-wrap gap-2 mt-1">
          {STEP_KIND_OPTIONS.map((s) => {
            const checked = stepKinds.includes(s);
            const isMeta = s === "next_step" || s === "extract_goal";
            return (
              <label
                key={s}
                className={`px-2 py-1 rounded cursor-pointer ${T.tiny} ${
                  checked
                    ? isMeta
                      ? "bg-amber-700 text-white"
                      : "bg-blue-700 text-white"
                    : isMeta
                      ? "bg-navy-800 text-amber-300 border border-amber-700/40"
                      : "bg-navy-800 text-slate-300 border border-navy-600"
                }`}
              >
                <input
                  type="checkbox"
                  className="hidden"
                  checked={checked}
                  onChange={(e) => {
                    if (e.target.checked) setStepKinds((p) => [...p, s]);
                    else setStepKinds((p) => p.filter((x) => x !== s));
                  }}
                />
                {s}
              </label>
            );
          })}
        </div>
        {stepKinds.some((s) => STEP_KIND_HINT[s]) && (
          <ul className="mt-2 space-y-1">
            {stepKinds
              .filter((s) => STEP_KIND_HINT[s])
              .map((s) => (
                <li key={s} className={`${T.tiny} text-amber-300/85 italic`}>
                  {STEP_KIND_HINT[s]}
                </li>
              ))}
          </ul>
        )}
      </div>
      <div>
        <div className="flex items-center justify-between">
          <label className={`${T.tiny} text-slate-300`}>
            System-Prompt-Erweiterung
          </label>
          <button
            type="button"
            onClick={() => setShowFullEditor(true)}
            className={`${T.tiny} text-blue-300 hover:text-blue-200 flex items-center gap-1`}
          >
            <Maximize2 className="w-3 h-3" aria-hidden /> Vollbild
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder={
            "Kurze Heuristik hier eintippen ODER auf 'Vollbild' für längere Prompts."
          }
          className={`mt-1 w-full px-2 py-1.5 rounded bg-navy-900 border border-navy-600 text-white text-[12px] leading-snug font-mono resize-y`}
        />
        <p className={`${T.tiny} text-slate-500 mt-0.5`}>
          {text.length} Zeichen
        </p>
      </div>
      <FullscreenTextEditor
        open={showFullEditor}
        title={`Approach: ${name || "(unbenannt)"}`}
        subtitle="System-Prompt-Erweiterung — wird an die Step-Prompts angehängt"
        initialText={text}
        onSave={(newText) => {
          setText(newText);
          setShowFullEditor(false);
        }}
        onClose={() => setShowFullEditor(false)}
        placeholder={
          "Beispiel:\n\n" +
          "ARBEITSWEISE BEI CHUNK-KNOTEN\n\n" +
          "1. Inhalt vollständig erfassen.\n" +
          "2. Mit Sitzungs-Ziel abgleichen.\n" +
          "3. Nächsten Schritt aus den verfügbaren Steps wählen.\n" +
          "..."
        }
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={
            create.isPending || !name.trim() || stepKinds.length === 0 || !text.trim()
          }
          className={`px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {create.isPending ? "Erstelle…" : "Erstellen"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className={`px-3 py-1.5 rounded text-slate-300 hover:bg-navy-700 ${T.body}`}
        >
          Abbrechen
        </button>
      </div>
      {create.error && (
        <p className={`text-red-400 ${T.tiny}`}>{create.error.message}</p>
      )}
    </div>
  );
}

function ApproachRow({
  approach,
  token,
}: {
  approach: Approach;
  token: string;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(approach.extra_system);
  const [showFullEditor, setShowFullEditor] = useState(false);
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
  async function handleSaveText(): Promise<void> {
    try {
      await patch.mutateAsync({
        approachId: approach.approach_id,
        patch: { extra_system: text.trim() },
      });
      setEditing(false);
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
      {!editing ? (
        <div className="mt-2 relative group">
          <pre
            onClick={() => setEditing(true)}
            className="p-2 rounded bg-navy-950 text-slate-200 text-[11px] font-mono whitespace-pre-wrap break-words cursor-text hover:bg-navy-900"
            title="Klicken zum Bearbeiten"
          >
            {approach.extra_system}
          </pre>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setText(approach.extra_system);
              setShowFullEditor(true);
            }}
            className={`absolute top-1 right-1 px-2 py-0.5 rounded bg-navy-800/90 text-blue-300 hover:text-blue-200 hover:bg-navy-700 ${T.tiny} flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity`}
            title="Im Vollbild bearbeiten"
          >
            <Maximize2 className="w-3 h-3" aria-hidden /> Vollbild
          </button>
        </div>
      ) : (
        <div className="mt-2 space-y-1">
          <div className="flex items-center justify-between">
            <span className={`${T.tiny} text-slate-400`}>
              Bearbeiten — Speichern bumpt Version v
              {approach.version + 1}
            </span>
            <button
              type="button"
              onClick={() => setShowFullEditor(true)}
              className={`${T.tiny} text-blue-300 hover:text-blue-200 flex items-center gap-1`}
            >
              <Maximize2 className="w-3 h-3" aria-hidden /> Vollbild
            </button>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            className={`w-full px-2 py-1.5 rounded bg-navy-900 border border-navy-600 text-white text-[12px] leading-snug font-mono resize-y`}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleSaveText()}
              disabled={patch.isPending}
              className={`px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.tiny}`}
            >
              {patch.isPending ? "…" : "Speichern"}
            </button>
            <button
              type="button"
              onClick={() => {
                setText(approach.extra_system);
                setEditing(false);
              }}
              className={`px-3 py-1.5 rounded text-slate-300 hover:bg-navy-700 ${T.tiny}`}
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
      {patch.error && (
        <p className={`text-red-400 ${T.tiny} mt-1`}>{patch.error.message}</p>
      )}
      <FullscreenTextEditor
        open={showFullEditor}
        title={`Approach: ${approach.name}`}
        subtitle={`v${approach.version} → v${approach.version + 1} · ${approach.step_kinds.join(", ")}`}
        initialText={text}
        onSave={async (newText) => {
          setText(newText);
          // Persist immediately when saving from the modal — saves the
          // user a second click; modal closes after.
          try {
            await patch.mutateAsync({
              approachId: approach.approach_id,
              patch: { extra_system: newText.trim() },
            });
            setEditing(false);
            setShowFullEditor(false);
          } catch {
            // error surfaces in the patch.error block below the row
          }
        }}
        onClose={() => setShowFullEditor(false)}
        saveLabel={patch.isPending ? "Speichere…" : "Speichern"}
      />
    </li>
  );
}

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

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

      <ul className="mt-3 space-y-2">
        {approaches?.map((a) => (
          <ApproachRow key={a.approach_id} approach={a} token={token} />
        ))}
      </ul>
    </div>
  );
}

function CreateForm({ token, onDone }: { token: string; onDone: () => void }): JSX.Element {
  const [name, setName] = useState("");
  const [stepKinds, setStepKinds] = useState<string[]>(["extract_claims"]);
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
        <label className={`${T.tiny} text-slate-300 block`}>System-Prompt-Erweiterung</label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Sei besonders gründlich bei Zahlen und Einheiten…"
          className={`mt-0.5 w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body} font-mono`}
        />
      </div>
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
        <pre
          onClick={() => setEditing(true)}
          className="mt-2 p-2 rounded bg-navy-950 text-slate-200 text-[11px] font-mono whitespace-pre-wrap break-words cursor-text hover:bg-navy-900"
          title="Klicken zum Bearbeiten"
        >
          {approach.extra_system}
        </pre>
      ) : (
        <div className="mt-2 space-y-1">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white text-[11px] font-mono`}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleSaveText()}
              disabled={patch.isPending}
              className={`px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.tiny}`}
            >
              {patch.isPending ? "…" : "Speichern (v" + (approach.version + 1) + ")"}
            </button>
            <button
              type="button"
              onClick={() => {
                setText(approach.extra_system);
                setEditing(false);
              }}
              className={`px-2 py-1 rounded text-slate-300 hover:bg-navy-700 ${T.tiny}`}
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
      {patch.error && (
        <p className={`text-red-400 ${T.tiny} mt-1`}>{patch.error.message}</p>
      )}
    </li>
  );
}

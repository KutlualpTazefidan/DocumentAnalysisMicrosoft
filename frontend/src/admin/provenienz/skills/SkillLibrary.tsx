import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteSkill,
  useSkills,
  useUpdateSkill,
  type Skill,
  type SkillKind,
} from "../../hooks/useSkills";
import { T } from "../../styles/typography";
import { TemplatePicker, type TemplateKind } from "./TemplatePicker";

interface Props {
  token: string;
}

/**
 * Unified Skill library — the post-migration successor of
 * {@link ApproachLibrary}. Lists every skill (enabled + disabled),
 * grouped by `skill_kind`. The "+ Neu" button is wired to a stub
 * here; Task 13 connects it to the TemplatePicker modal, and Task 16
 * replaces the stub Edit button with an actual form.
 */
export function SkillLibrary({ token }: Props): JSX.Element {
  const { data: skills, isLoading, error } = useSkills(token);
  const [pickerOpen, setPickerOpen] = useState(false);

  function handleTemplate(template: TemplateKind): void {
    // Tasks 14-16 replace this with the actual template form modals.
    setPickerOpen(false);
    window.alert(`Template-Form für ${template} kommt in Task 14-16`);
  }

  return (
    <div className="border border-navy-700 rounded-lg bg-navy-800/40 p-4">
      <header className="flex items-center justify-between mb-2">
        <div>
          <h3 className={`${T.heading} text-white`}>Skill-Bibliothek</h3>
          <p className={`${T.body} text-slate-400`}>
            Eine Skill ergänzt Logik des Provenienz-Agents — kein Code
            nötig. Anreicherungen, Prompt-Erweiterungen, reaktive Regeln,
            Lehr-Notizen oder aktive Sub-Agents.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className={`px-3 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} flex items-center gap-1 shrink-0`}
        >
          <Plus className="w-4 h-4" /> Neu
        </button>
      </header>

      {isLoading && <p className={`${T.body} text-slate-400 mt-3`}>Lade…</p>}
      {error && (
        <p className={`${T.body} text-red-400 mt-3`}>{error.message}</p>
      )}
      {skills && skills.length === 0 && !isLoading && (
        <p className={`${T.body} text-slate-500 italic mt-3`}>
          Noch keine Skills definiert.
        </p>
      )}

      <SkillKindGroups skills={skills ?? []} token={token} />

      <TemplatePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={handleTemplate}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

const SKILL_KIND_ORDER: SkillKind[] = [
  "enrichment",
  "prompt-overlay",
  "reactive",
  "note",
  "subagent",
];

const SKILL_KIND_LABEL: Record<SkillKind, string> = {
  enrichment: "📜 Aussage anreichern",
  "prompt-overlay": "🔍 Prompt-Erweiterungen",
  reactive: "⚖ Reaktive Bewertungs-Regeln",
  note: "📌 Lehr-Notizen",
  subagent: "🧠 Aktive Sub-Agents",
};

const SKILL_KIND_BADGE: Record<SkillKind, string> = {
  enrichment: "bg-cyan-700 text-white",
  "prompt-overlay": "bg-blue-700 text-white",
  reactive: "bg-orange-700 text-white",
  note: "bg-zinc-600 text-white",
  subagent: "bg-emerald-700 text-white",
};

function SkillKindGroups({
  skills,
  token,
}: {
  skills: Skill[];
  token: string;
}): JSX.Element {
  const groups = new Map<SkillKind, Skill[]>();
  for (const s of skills) {
    if (!groups.has(s.skill_kind)) groups.set(s.skill_kind, []);
    groups.get(s.skill_kind)!.push(s);
  }
  const ordered: SkillKind[] = [
    ...SKILL_KIND_ORDER.filter((k) => groups.has(k)),
    // Defensive: any unexpected kind from the server still gets rendered.
    ...[...groups.keys()].filter((k) => !SKILL_KIND_ORDER.includes(k)),
  ];
  if (ordered.length === 0) return <></>;
  return (
    <div className="mt-3 space-y-3">
      {ordered.map((kind) => (
        <SkillKindGroup
          key={kind}
          kind={kind}
          skills={groups.get(kind) ?? []}
          token={token}
        />
      ))}
    </div>
  );
}

function SkillKindGroup({
  kind,
  skills,
  token,
}: {
  kind: SkillKind;
  skills: Skill[];
  token: string;
}): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);
  const enabledCount = skills.filter((s) => s.enabled).length;
  const label = SKILL_KIND_LABEL[kind] ?? kind;
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
            {skills.length} ({enabledCount} aktiv)
          </span>
        </div>
      </button>
      {!collapsed && (
        <ul className="px-3 pb-3 space-y-2">
          {skills.map((s) => (
            <SkillRow key={s.skill_id} skill={s} token={token} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function SkillRow({ skill, token }: { skill: Skill; token: string }): JSX.Element {
  const update = useUpdateSkill(token);
  const del = useDeleteSkill(token);
  const { error: toastError } = useToast();

  async function handleToggle(): Promise<void> {
    try {
      await update.mutateAsync({
        skill_id: skill.skill_id,
        patch: { enabled: !skill.enabled },
      });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  function handleEdit(): void {
    // Placeholder — Task 16 replaces this with the appropriate template form.
    window.alert(`Edit-Form für "${skill.name}" — folgt in Task 16.`);
  }

  async function handleDelete(): Promise<void> {
    if (!window.confirm(`Skill "${skill.name}" löschen?`)) return;
    try {
      await del.mutateAsync(skill.skill_id);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  const badgeClass = SKILL_KIND_BADGE[skill.skill_kind] ?? "bg-zinc-700 text-white";

  return (
    <li
      className={`rounded border p-3 ${
        skill.enabled
          ? "border-navy-600 bg-navy-900/40"
          : "border-navy-700 bg-navy-900/20 opacity-60"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-white font-semibold flex items-center gap-2 flex-wrap">
            {skill.name}{" "}
            <span className={`${T.tiny} text-slate-400 font-normal`}>
              v{skill.version}
            </span>
            <span
              className={`px-1.5 py-px rounded text-[10px] font-semibold ${badgeClass}`}
              title={`skill_kind = ${skill.skill_kind}`}
            >
              {skill.skill_kind}
            </span>
            {skill.parent_skill && (
              <span
                className="px-1.5 py-px rounded text-[10px] font-mono bg-orange-900/50 text-orange-200"
                title={`Sub-Skill von ${skill.parent_skill}`}
              >
                ↳ {skill.parent_skill}
              </span>
            )}
          </p>
          {skill.fires_on.length > 0 && (
            <p className={`${T.tiny} text-slate-400`}>
              Bei: {skill.fires_on.join(", ")}
            </p>
          )}
          {skill.description && (
            <p className={`${T.tiny} text-slate-300 mt-1`}>{skill.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleEdit}
            className={`px-2 py-0.5 rounded text-blue-300 hover:bg-blue-900/30 ${T.tiny} flex items-center gap-1`}
            aria-label="Bearbeiten"
            title="Skill bearbeiten"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit
          </button>
          <button
            type="button"
            onClick={() => void handleToggle()}
            disabled={update.isPending}
            className={`px-2 py-0.5 rounded ${T.tiny} ${
              skill.enabled
                ? "bg-emerald-700 text-white hover:bg-emerald-600"
                : "bg-zinc-700 text-slate-300 hover:bg-zinc-600"
            }`}
          >
            {skill.enabled ? "aktiv" : "inaktiv"}
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
      {update.error && (
        <p className={`text-red-400 ${T.tiny} mt-1`}>{update.error.message}</p>
      )}
    </li>
  );
}

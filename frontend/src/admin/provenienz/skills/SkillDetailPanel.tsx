import { useEffect, useState } from "react";
import { Pencil, Trash2, X } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteSkill,
  useUpdateSkill,
  type Skill,
} from "../../hooks/useSkills";
import { T } from "../../styles/typography";
import { CustomForm } from "./templates/CustomForm";

interface SkillDetailPanelProps {
  /** When non-null, the panel is rendered for the given skill. */
  skill: Skill | null;
  onClose: () => void;
  token: string;
}

/**
 * SkillDetailPanel — read-only summary of a Skill plus the three
 * mutating actions (Edit / Toggle enabled / Delete). Edit reuses
 * {@link CustomForm} in PATCH mode (the power-user form is the
 * superset of every template, so it works for every skill_kind).
 */
export function SkillDetailPanel({
  skill,
  onClose,
  token,
}: SkillDetailPanelProps): JSX.Element | null {
  const update = useUpdateSkill(token);
  const del = useDeleteSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();
  const [editing, setEditing] = useState(false);

  // Reset edit-mode whenever the panel opens for a different skill.
  useEffect(() => {
    setEditing(false);
  }, [skill?.skill_id]);

  // ESC closes the panel (when not editing — the edit modal handles its own ESC).
  useEffect(() => {
    if (!skill || editing) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [skill, editing, onClose]);

  if (!skill) return null;

  async function handleToggle(): Promise<void> {
    if (!skill) return;
    try {
      await update.mutateAsync({
        skill_id: skill.skill_id,
        patch: { enabled: !skill.enabled },
      });
      toastSuccess(
        skill.enabled
          ? `Skill "${skill.name}" deaktiviert.`
          : `Skill "${skill.name}" aktiviert.`,
      );
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleDelete(): Promise<void> {
    if (!skill) return;
    if (!window.confirm(`Skill "${skill.name}" löschen?`)) return;
    try {
      await del.mutateAsync(skill.skill_id);
      toastSuccess(`Skill "${skill.name}" gelöscht.`);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  // While the edit-overlay is open, we hide the detail-panel modal
  // chrome behind it (the edit form is a self-contained modal).
  if (editing) {
    return (
      <CustomForm
        open
        onClose={() => setEditing(false)}
        token={token}
        initialSkill={skill}
      />
    );
  }

  const hasFiresOn = skill.fires_on.length > 0;
  const conditions = skill.conditions;
  const output = skill.output;
  const prompt = skill.prompt;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Skill ${skill.name}`}
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(900px,95vw)] h-[min(800px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate flex items-center gap-2`}>
              {skill.name}
              <span className={`${T.tiny} text-slate-400 font-normal`}>
                v{skill.version}
              </span>
              <span
                className="px-1.5 py-px rounded text-[10px] font-semibold bg-zinc-700 text-white"
                title={`skill_kind = ${skill.skill_kind}`}
              >
                {skill.skill_kind}
              </span>
              {!skill.enabled && (
                <span className="px-1.5 py-px rounded text-[10px] font-semibold bg-zinc-800 text-slate-400">
                  inaktiv
                </span>
              )}
            </h2>
            {skill.description && (
              <p className={`${T.tiny} text-slate-400 mt-0.5`}>
                {skill.description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded shrink-0"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
          <DetailSection title="Wann (fires_on)">
            {hasFiresOn ? (
              <div className="flex flex-wrap gap-1.5">
                {skill.fires_on.map((step) => (
                  <span
                    key={step}
                    className={`px-2 py-0.5 rounded bg-blue-900/40 text-blue-200 ${T.tiny} font-mono`}
                  >
                    {step}
                  </span>
                ))}
              </div>
            ) : (
              <p className={`${T.tiny} text-slate-500 italic`}>
                Keine Schritte konfiguriert — Skill feuert nie.
              </p>
            )}
          </DetailSection>

          {(prompt.free_text ||
            prompt.questions.length > 0 ||
            prompt.domain_rules) && (
            <DetailSection title="Prompt">
              {prompt.free_text && (
                <Field label="free_text">
                  <pre
                    className={`${T.tiny} text-slate-200 font-mono whitespace-pre-wrap break-words bg-navy-950/50 rounded px-2 py-1.5`}
                  >
                    {prompt.free_text}
                  </pre>
                </Field>
              )}
              {prompt.questions.length > 0 && (
                <Field label={`questions (${prompt.questions.length})`}>
                  <ul className={`${T.tiny} text-slate-200 list-disc pl-5 space-y-0.5`}>
                    {prompt.questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </Field>
              )}
              {prompt.domain_rules && (
                <Field label="domain_rules">
                  <pre
                    className={`${T.tiny} text-slate-200 font-mono whitespace-pre-wrap break-words bg-navy-950/50 rounded px-2 py-1.5`}
                  >
                    {prompt.domain_rules}
                  </pre>
                </Field>
              )}
            </DetailSection>
          )}

          {hasNonEmptyConditions(conditions) && (
            <DetailSection title="Bedingungen (Trigger)">
              {conditions.verdicts.length > 0 && (
                <Field label="verdicts">
                  <Chips items={conditions.verdicts} tone="orange" />
                </Field>
              )}
              {conditions.sentence_regex.length > 0 && (
                <Field label="sentence_regex">
                  <Chips items={conditions.sentence_regex} tone="amber" mono />
                </Field>
              )}
              {conditions.claim_regex.length > 0 && (
                <Field label="claim_regex">
                  <Chips items={conditions.claim_regex} tone="amber" mono />
                </Field>
              )}
              {conditions.topic_keywords.length > 0 && (
                <Field label="topic_keywords">
                  <Chips items={conditions.topic_keywords} tone="slate" />
                </Field>
              )}
              {conditions.anchor_kinds.length > 0 && (
                <Field label="anchor_kinds">
                  <Chips items={conditions.anchor_kinds} tone="amber" mono />
                </Field>
              )}
              {conditions.goal_contains.length > 0 && (
                <Field label="goal_contains">
                  <Chips items={conditions.goal_contains} tone="slate" />
                </Field>
              )}
              {conditions.text_contains.length > 0 && (
                <Field label="text_contains">
                  <Chips items={conditions.text_contains} tone="slate" />
                </Field>
              )}
            </DetailSection>
          )}

          {(output.annotation_kind ||
            output.attaches_to ||
            output.consumed_by.length > 0) && (
            <DetailSection title="Output (Annotation)">
              {output.annotation_kind && (
                <Field label="annotation_kind">
                  <code
                    className={`${T.tiny} font-mono text-cyan-200 bg-navy-950/50 rounded px-1.5 py-0.5`}
                  >
                    {output.annotation_kind}
                  </code>
                </Field>
              )}
              {output.attaches_to && (
                <Field label="attaches_to">
                  <code
                    className={`${T.tiny} font-mono text-cyan-200 bg-navy-950/50 rounded px-1.5 py-0.5`}
                  >
                    {output.attaches_to}
                  </code>
                </Field>
              )}
              {output.consumed_by.length > 0 && (
                <Field label="consumed_by">
                  <Chips items={output.consumed_by} tone="cyan" mono />
                </Field>
              )}
            </DetailSection>
          )}

          {skill.parent_skill && (
            <DetailSection title="Hierarchie">
              <Field label="parent_skill">
                <code
                  className={`${T.tiny} font-mono text-orange-200 bg-orange-950/30 rounded px-1.5 py-0.5`}
                >
                  {skill.parent_skill}
                </code>
              </Field>
            </DetailSection>
          )}

          <details className="rounded border border-navy-700 bg-navy-900/30">
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-slate-400`}
            >
              Roh-Daten anzeigen
            </summary>
            <pre
              className={`px-3 pb-3 pt-1 ${T.tiny} text-slate-300 font-mono whitespace-pre-wrap break-all`}
            >
              {JSON.stringify(skill, null, 2)}
            </pre>
          </details>

          {(update.error || del.error) && (
            <p className={`${T.body} text-red-400`}>
              {(update.error ?? del.error)?.message}
            </p>
          )}
        </div>

        <footer className="px-4 py-3 border-t border-navy-700 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => void handleDelete()}
            disabled={del.isPending}
            className={`px-3 py-1.5 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} flex items-center gap-1 disabled:opacity-50`}
          >
            <Trash2 className="w-4 h-4" />
            {del.isPending ? "…" : "Löschen"}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleToggle()}
              disabled={update.isPending}
              className={`px-3 py-1.5 rounded ${T.body} disabled:opacity-50 ${
                skill.enabled
                  ? "bg-zinc-700 text-slate-200 hover:bg-zinc-600"
                  : "bg-emerald-700 text-white hover:bg-emerald-600"
              }`}
            >
              {update.isPending
                ? "…"
                : skill.enabled
                  ? "Deaktivieren"
                  : "Aktivieren"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold flex items-center gap-1`}
            >
              <Pencil className="w-4 h-4" /> Bearbeiten
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

function hasNonEmptyConditions(c: Skill["conditions"]): boolean {
  return (
    c.verdicts.length > 0 ||
    c.sentence_regex.length > 0 ||
    c.claim_regex.length > 0 ||
    c.topic_keywords.length > 0 ||
    c.anchor_kinds.length > 0 ||
    c.goal_contains.length > 0 ||
    c.text_contains.length > 0
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <fieldset className="rounded border border-navy-700 bg-navy-900/30 px-3 pt-2 pb-3 space-y-2">
      <legend className={`${T.tinyBold} text-slate-200 px-1`}>{title}</legend>
      {children}
    </fieldset>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div>
      <p className={`${T.tinyBold} text-slate-300 mb-0.5`}>{label}</p>
      {children}
    </div>
  );
}

const CHIP_TONES: Record<string, string> = {
  slate: "bg-navy-800 text-slate-200 border border-navy-600",
  amber: "bg-amber-900/40 text-amber-200",
  orange: "bg-orange-900/40 text-orange-200",
  cyan: "bg-cyan-900/40 text-cyan-200",
};

function Chips({
  items,
  tone = "slate",
  mono = false,
}: {
  items: string[];
  tone?: keyof typeof CHIP_TONES | string;
  mono?: boolean;
}): JSX.Element {
  const cls = CHIP_TONES[tone] ?? CHIP_TONES.slate;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span
          key={`${it}-${i}`}
          className={`px-2 py-0.5 rounded ${T.tiny} ${mono ? "font-mono" : ""} ${cls}`}
        >
          {it}
        </span>
      ))}
    </div>
  );
}

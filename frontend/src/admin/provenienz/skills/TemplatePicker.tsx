import { useEffect } from "react";
import { X } from "lucide-react";

import { T } from "../../styles/typography";

/**
 * Six template kinds the user can pick from "+ Neu". Five preset shapes
 * cover ~95% of cases; "custom" exposes the full form (Task 16).
 *
 * Note: `agent-rule` is a UX label for a `subagent`-kind skill scoped
 * to `next_step`. Mapping happens in the corresponding template form
 * (Task 15) — the picker only emits the kind the user picked.
 */
export type TemplateKind =
  | "enrichment"
  | "prompt-overlay"
  | "reactive"
  | "note"
  | "agent-rule"
  | "custom";

interface TemplatePickerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (template: TemplateKind) => void;
}

interface TemplateCard {
  kind: TemplateKind;
  emoji: string;
  title: string;
  description: string;
}

const TEMPLATES: TemplateCard[] = [
  {
    kind: "enrichment",
    emoji: "📜",
    title: "Aussage anreichern",
    description:
      "Holt zusätzliche Infos aus dem Chunk, schreibt sie an die Aussage. " +
      "Beispiel: Reaktor-Typ, Werte-Klasse, Standort.",
  },
  {
    kind: "prompt-overlay",
    emoji: "🔍",
    title: "Such-Anfrage verbessern",
    description: "Lehrt den Agent, wie er Anfragen für ein Thema formuliert.",
  },
  {
    kind: "reactive",
    emoji: "⚖",
    title: "Bewertung neu fassen",
    description:
      "Reagiert auf bestimmte Verdicts und wendet Domain-Wissen an.",
  },
  {
    kind: "note",
    emoji: "📌",
    title: "Lehr-Notiz",
    description:
      "Kurze Regel, die in alle Prompts eines Step-Typs aufgenommen wird.",
  },
  {
    kind: "agent-rule",
    emoji: "🧠",
    title: "Agent-Denkregel",
    description: "Beeinflusst, WIE der Agent den nächsten Schritt wählt.",
  },
  {
    kind: "custom",
    emoji: "🛠",
    title: "Eigener Skill",
    description: "Für Power-User. Volle Kontrolle über alle Felder.",
  },
];

export function TemplatePicker({
  open,
  onClose,
  onSelect,
}: TemplatePickerProps): JSX.Element | null {
  // ESC closes — nice-to-have per plan. Only attaches while open.
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Skill-Template wählen"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <h2 className={`${T.heading} text-white`}>Was soll dein Skill tun?</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {TEMPLATES.map((tpl) => (
              <button
                key={tpl.kind}
                type="button"
                onClick={() => onSelect(tpl.kind)}
                className="group text-left border border-navy-600 hover:border-blue-400 hover:bg-navy-800/60 rounded-lg p-4 transition-colors flex flex-col gap-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-2xl leading-none">{tpl.emoji}</span>
                  <span className="text-slate-500 group-hover:text-blue-300 text-lg leading-none">
                    →
                  </span>
                </div>
                <p className={`${T.body} font-semibold text-white mt-1`}>
                  {tpl.title}
                </p>
                <p className={`${T.tiny} text-slate-400`}>{tpl.description}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

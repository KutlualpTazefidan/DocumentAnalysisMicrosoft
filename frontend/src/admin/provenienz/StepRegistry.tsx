import { Brain, Wrench } from "lucide-react";

import type { AgentInfo, AgentStepInfo } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  info: AgentInfo;
  /** Called with ``"step:<kind>"`` to navigate to the Auswahl tab with
   *  the step's full system-prompt + rules opened. */
  onSelect: (id: string) => void;
}

/**
 * Reference list of every LLM-call (and the one tool-call) the agent
 * uses. Distinct from Werkzeuge (deterministic tools) and Heuristiken
 * (prompt-overlays) — this tab is the "what does the agent literally
 * call" inventory. Most useful when authoring approaches: the
 * step_kinds field on an Approach maps 1:1 to the rows shown here.
 */
export function StepRegistry({ info, onSelect }: Props): JSX.Element {
  // The Meta-Planer lives on info.next_step (separate slot), every
  // other step on info.steps. Render them as one combined list so the
  // user sees the full inventory in one scan.
  const next: AgentStepInfo = { ...info.next_step, user_template: "" };
  const all = [next, ...info.steps];

  return (
    <div className="space-y-3">
      <header>
        <h3 className={`${T.heading} text-ink`}>Schritte (LLM-Calls)</h3>
        <p className={`${T.body} text-ink-muted`}>
          Alle vom Agent ausgelösten LLM-Aufrufe.
          <code className="text-amber-700 mx-1">step_kinds</code>
          in einer Approach binden sich an diese Kennungen — wähle hier was du
          beeinflussen willst, dann verweist deine Approach den passenden
          Step.
        </p>
        <p className={`${T.tiny} text-ink-muted mt-1`}>
          Klick auf eine Zeile springt in die Auswahl mit System-Prompt
          und Regeln im Detail.
        </p>
      </header>
      <ul className="space-y-1.5">
        {all.map((s) => (
          <StepRow key={s.kind} step={s} onSelect={onSelect} />
        ))}
      </ul>
      <p className={`${T.tiny} text-ink-muted italic`}>
        Phase-3-interne Helfer (active_skill, coordinator) erscheinen hier
        bewusst nicht — sie sind keine eigenständig auswählbaren Schritte,
        sondern Stationen im next_step-Pipeline. Im Live-Lauf-Panel sind
        sie als L2-/L3-Karten sichtbar.
      </p>
    </div>
  );
}

function StepRow({
  step,
  onSelect,
}: {
  step: AgentStepInfo;
  onSelect: (id: string) => void;
}): JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(`step:${step.kind}`)}
        className="w-full text-left rounded border border-line bg-canvas hover:bg-white p-2.5 transition-colors"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <ModeBadge usesLlm={step.uses_llm} usesTool={step.uses_tool} />
          <span className="font-mono text-blue-700 font-semibold">
            {step.kind}
          </span>
          <span className={`${T.body} text-ink`}>{step.label}</span>
          {step.uses_tool && (
            <span
              className={`${T.tiny} font-mono text-emerald-700`}
              title="Dieses Step ruft ein Werkzeug auf"
            >
              · {step.uses_tool}
            </span>
          )}
        </div>
        <p className={`${T.tiny} text-ink-muted mt-1 font-mono`}>
          {step.input_kind}
          <span className="text-ink-muted mx-1">→</span>
          {step.output_kind}
        </p>
        {step.system_prompt && (
          <details
            className="mt-1.5"
            onClick={(e) => e.stopPropagation()}
          >
            <summary
              className={`${T.tiny} text-ink-muted cursor-pointer hover:text-ink`}
            >
              System-Prompt-Vorschau
            </summary>
            <pre className="mt-1 p-1.5 rounded bg-canvas text-[10px] text-ink-muted whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
              {step.system_prompt}
            </pre>
          </details>
        )}
      </button>
    </li>
  );
}

function ModeBadge({
  usesLlm,
  usesTool,
}: {
  usesLlm: boolean;
  usesTool: string | null;
}): JSX.Element {
  if (usesLlm) {
    return (
      <span
        className="px-1.5 py-px rounded text-[10px] font-semibold bg-blue-100 text-blue-800 flex items-center gap-1"
        title="Eigener LLM-Call"
      >
        <Brain className="w-3 h-3" aria-hidden /> LLM
      </span>
    );
  }
  if (usesTool) {
    return (
      <span
        className="px-1.5 py-px rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1"
        title="Werkzeug-Aufruf, kein LLM"
      >
        <Wrench className="w-3 h-3" aria-hidden /> Tool
      </span>
    );
  }
  return (
    <span className="px-1.5 py-px rounded text-[10px] font-semibold bg-zinc-100 text-zinc-700">
      —
    </span>
  );
}

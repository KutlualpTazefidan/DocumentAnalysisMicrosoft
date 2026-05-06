import { Bot } from "lucide-react";

import { T } from "../../styles/typography";

interface AuditPayload {
  source_label?: string;
  system_prompt_used?: string;
  input_summary?: {
    anchor_kind?: string;
    anchor_text_preview?: string;
    session_goal?: string;
    available_steps?: string[];
    tools_summary?: string;
  };
  guidance_consulted?: { kind: string; id: string; summary: string }[];
}

interface Props {
  audit: AuditPayload | undefined;
}

/**
 * Shared "Quelle" / audit block used by PlanProposalPanel,
 * CapabilityRequestPanel, ManualReviewPanel. Surfaces the full LLM
 * input — system prompt + input summary + guidance refs — so the user
 * can trace exactly where the agent's reasoning came from instead of
 * having to trust a free-text sentence.
 */
export function AgentAuditSection({ audit }: Props): JSX.Element | null {
  if (!audit) return null;
  const inp = audit.input_summary ?? {};
  return (
    <section className="rounded border border-slate-700 bg-navy-950/60 p-3 space-y-2">
      <header className="flex items-center gap-1.5">
        <Bot className="w-3.5 h-3.5 text-slate-300" aria-hidden />
        <p className={`${T.tinyBold} text-slate-300`}>Quelle (Agent-Reasoning)</p>
      </header>
      {audit.source_label && (
        <p className={`${T.tiny} text-slate-400 italic`}>{audit.source_label}</p>
      )}
      {(inp.anchor_kind || inp.anchor_text_preview) && (
        <div>
          <p className={T.tinyBold}>Eingabe-Knoten</p>
          {inp.anchor_kind && (
            <p className={`${T.tiny} text-slate-300 font-mono`}>
              kind = {inp.anchor_kind}
            </p>
          )}
          {inp.anchor_text_preview && (
            <p className={`${T.tiny} text-slate-200 italic line-clamp-3 mt-0.5`}>
              „{inp.anchor_text_preview}"
            </p>
          )}
        </div>
      )}
      {inp.session_goal !== undefined && (
        <div>
          <p className={T.tinyBold}>Sitzungs-Ziel</p>
          <p className={`${T.tiny} text-slate-300 italic`}>
            {inp.session_goal || "(nicht gesetzt)"}
          </p>
        </div>
      )}
      {inp.available_steps && inp.available_steps.length > 0 && (
        <div>
          <p className={T.tinyBold}>Verfügbare Steps für diesen Knoten</p>
          <p className={`${T.tiny} text-slate-300 font-mono`}>
            {inp.available_steps.join(" · ")}
          </p>
        </div>
      )}
      {inp.tools_summary && (
        <details className="rounded bg-navy-900 border border-navy-700">
          <summary className={`${T.tinyBold} cursor-pointer px-2 py-1`}>
            Tool-Liste die der Agent gesehen hat
          </summary>
          <pre className="px-2 pb-2 text-[10px] text-slate-300 whitespace-pre-wrap break-words font-mono">
            {inp.tools_summary}
          </pre>
        </details>
      )}
      {audit.guidance_consulted && audit.guidance_consulted.length > 0 && (
        <div>
          <p className={T.tinyBold}>Konsultierte Hinweise</p>
          <ul className="mt-1 space-y-0.5">
            {audit.guidance_consulted.map((g, i) => (
              <li key={i} className={`${T.tiny} text-slate-300`}>
                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wide ${
                    g.kind === "approach"
                      ? "bg-purple-900/60 text-purple-200"
                      : "bg-amber-900/60 text-amber-200"
                  }`}
                >
                  {g.kind}
                </span>{" "}
                {g.summary}
              </li>
            ))}
          </ul>
        </div>
      )}
      {audit.system_prompt_used && (
        <details className="rounded bg-navy-900 border border-navy-700">
          <summary className={`${T.tinyBold} cursor-pointer px-2 py-1`}>
            System-Prompt (mit Heuristik-Overlays)
          </summary>
          <pre className="px-2 pb-2 text-[10px] text-slate-200 whitespace-pre-wrap break-words font-mono">
            {audit.system_prompt_used}
          </pre>
        </details>
      )}
    </section>
  );
}

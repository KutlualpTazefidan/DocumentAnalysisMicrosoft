import type {
  AgentInfo,
  AgentRuleInfo,
  AgentStepInfo,
  AgentToolInfo,
} from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  info: AgentInfo;
  selectedId: string | null;
  onClose: () => void;
}

/**
 * Side panel that reads ``selectedId`` from the canvas (e.g. "step:evaluate"
 * or "tool:InDocSearcher") and renders the corresponding details from the
 * agent-info payload. v1: read-only; editing prompts/models is a future
 * "live edit" feature with its own backend route.
 */
export function AgentInspector({ info, selectedId, onClose }: Props): JSX.Element {
  if (!selectedId) {
    return (
      <div className={`p-4 ${T.body} text-slate-500 italic`}>
        Tile auswählen, um Modell, Prompt, Tool und Regeln zu sehen.
      </div>
    );
  }
  if (selectedId.startsWith("step:")) {
    const kind = selectedId.slice("step:".length);
    const step = info.steps.find((s) => s.kind === kind);
    if (!step) return <NotFound onClose={onClose} />;
    return <StepView info={info} step={step} onClose={onClose} />;
  }
  if (selectedId.startsWith("tool:")) {
    const name = selectedId.slice("tool:".length);
    const tool = info.tools.find((t) => t.name === name);
    if (!tool) return <NotFound onClose={onClose} />;
    return <ToolView tool={tool} onClose={onClose} />;
  }
  if (selectedId.startsWith("data:")) {
    const kind = selectedId.slice("data:".length);
    return <DataView kind={kind} info={info} onClose={onClose} />;
  }
  return <NotFound onClose={onClose} />;
}

function StepView({
  info,
  step,
  onClose,
}: {
  info: AgentInfo;
  step: AgentStepInfo;
  onClose: () => void;
}): JSX.Element {
  return (
    <div className="flex flex-col h-full">
      <Header title={step.label} subtitle={step.kind} onClose={onClose} />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <Section title="Daten-Fluss">
          <p className={`text-slate-200 ${T.body}`}>
            <code className="text-blue-300">{step.input_kind}</code>
            {" → "}
            <code className="text-blue-300">{step.output_kind}</code>
          </p>
        </Section>

        {step.uses_llm && (
          <Section title="LLM">
            <p className={`text-slate-200 ${T.body}`}>
              <span className="text-slate-400">Backend:</span>{" "}
              <code className="text-amber-300">{info.llm.backend}</code>
            </p>
            <p className={`text-slate-200 ${T.body} mt-0.5`}>
              <span className="text-slate-400">Modell:</span>{" "}
              <code className="text-amber-300">{info.llm.model || "–"}</code>
            </p>
            {info.llm.base_url && (
              <p className={`text-slate-400 ${T.tiny} mt-0.5 break-all`}>
                {info.llm.base_url}
              </p>
            )}
          </Section>
        )}

        {step.uses_tool && (
          <Section title="Tool">
            <p className={`text-slate-200 ${T.body}`}>
              <code className="text-emerald-300">{step.uses_tool}</code>
            </p>
          </Section>
        )}

        {step.system_prompt && (
          <Section title="System-Prompt">
            <pre className="bg-navy-950 rounded p-2 text-[11px] text-slate-200 whitespace-pre-wrap break-words font-mono">
              {step.system_prompt}
            </pre>
          </Section>
        )}

        {step.user_template && (
          <Section title="User-Template">
            <pre className="bg-navy-950 rounded p-2 text-[11px] text-slate-200 whitespace-pre-wrap break-words font-mono">
              {step.user_template}
            </pre>
          </Section>
        )}

        <Section title="Erwartete Ausgabe">
          <p className={`text-slate-200 ${T.body}`}>{step.expected_output}</p>
        </Section>

        {step.rules.length > 0 && (
          <Section title="Aktive Regeln">
            <ul className="space-y-2">
              {step.rules.map((r) => {
                const rule = info.rules[r];
                if (!rule) {
                  return (
                    <li key={r} className={`${T.tiny} text-slate-300`}>
                      <code>{r}</code>
                    </li>
                  );
                }
                return <RulePill key={r} name={r} rule={rule} />;
              })}
            </ul>
          </Section>
        )}
      </div>
    </div>
  );
}

function ToolView({
  tool,
  onClose,
}: {
  tool: AgentToolInfo;
  onClose: () => void;
}): JSX.Element {
  return (
    <div className="flex flex-col h-full">
      <Header
        title={tool.label}
        subtitle={`${tool.scope} · ${tool.cost_hint}`}
        onClose={onClose}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <Section title="Status">
          <span
            className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-wide ${
              tool.enabled
                ? "bg-emerald-700 text-emerald-100"
                : "bg-zinc-700 text-zinc-300"
            }`}
          >
            {tool.enabled ? "aktiv" : "deaktiviert (Stub)"}
          </span>
        </Section>
        <Section title="Beschreibung">
          <p className={`text-slate-200 ${T.body}`}>{tool.description}</p>
        </Section>
        <Section title="Wann auswählen">
          <p className={`text-slate-200 ${T.body} italic`}>{tool.when_to_use}</p>
        </Section>
        <Section title="Verwendung">
          <p className={`text-slate-200 ${T.body}`}>
            Wird gerufen von:{" "}
            {tool.used_by.length === 0 ? (
              <span className="text-slate-500 italic">– (kein Step)</span>
            ) : (
              tool.used_by.map((s, i) => (
                <span key={s}>
                  <code className="text-blue-300">{s}</code>
                  {i < tool.used_by.length - 1 ? ", " : ""}
                </span>
              ))
            )}
          </p>
        </Section>
      </div>
    </div>
  );
}

function DataView({
  kind,
  info,
  onClose,
}: {
  kind: string;
  info: AgentInfo;
  onClose: () => void;
}): JSX.Element {
  const producedBy = info.steps.filter((s) => s.output_kind === kind);
  const consumedBy = info.steps.filter((s) => s.input_kind === kind || s.input_kind === "any");
  return (
    <div className="flex flex-col h-full">
      <Header title={kind} subtitle="Daten-Knoten" onClose={onClose} />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <Section title="Produziert von">
          {producedBy.length === 0 ? (
            <p className={`${T.body} text-slate-500 italic`}>– (Wurzel-Knoten)</p>
          ) : (
            <ul className="space-y-1">
              {producedBy.map((s) => (
                <li key={s.kind} className={`${T.body} text-slate-200`}>
                  <code className="text-blue-300">{s.kind}</code> · {s.label}
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Konsumiert von">
          {consumedBy.length === 0 ? (
            <p className={`${T.body} text-slate-500 italic`}>– (Endknoten)</p>
          ) : (
            <ul className="space-y-1">
              {consumedBy.map((s) => (
                <li key={s.kind} className={`${T.body} text-slate-200`}>
                  <code className="text-blue-300">{s.kind}</code> · {s.label}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </div>
  );
}

function RulePill({ name, rule }: { name: string; rule: AgentRuleInfo }): JSX.Element {
  return (
    <li className="rounded border border-navy-600 bg-navy-800/50 p-2">
      <p className={`${T.tinyBold} text-blue-300`}>{name}</p>
      <p className={`${T.body} text-slate-200 mt-0.5`}>{rule.summary}</p>
      <p className={`${T.tiny} text-slate-400 mt-1`}>
        <span className="text-slate-500">Auslöser:</span> {rule.trigger}
      </p>
      <p className={`${T.tiny} text-slate-400`}>
        <span className="text-slate-500">Speicher:</span>{" "}
        <code className="text-slate-300">{rule.storage}</code>
      </p>
      <p className={`${T.tiny} text-slate-400`}>
        <span className="text-slate-500">Injektion:</span> {rule.injection}
      </p>
    </li>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section>
      <p className={T.tinyBold}>{title}</p>
      <div className="mt-1">{children}</div>
    </section>
  );
}

function Header({
  title,
  subtitle,
  onClose,
}: {
  title: string;
  subtitle: string;
  onClose: () => void;
}): JSX.Element {
  return (
    <header className="px-4 py-3 border-b border-navy-700 flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className={T.tinyBold}>{subtitle}</p>
        <p className="text-white text-sm font-semibold truncate">{title}</p>
      </div>
      <button
        type="button"
        onClick={onClose}
        className={`text-slate-400 hover:text-white ${T.body}`}
        aria-label="Schließen"
      >
        ✕
      </button>
    </header>
  );
}

function NotFound({ onClose }: { onClose: () => void }): JSX.Element {
  return (
    <div className="flex flex-col h-full">
      <Header title="–" subtitle="unbekannt" onClose={onClose} />
      <div className="p-4">
        <p className={`${T.body} text-slate-500 italic`}>Nicht gefunden.</p>
      </div>
    </div>
  );
}

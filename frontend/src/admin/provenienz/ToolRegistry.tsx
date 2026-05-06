import { Wrench } from "lucide-react";

import type { AgentToolInfo } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  tools: AgentToolInfo[];
  onSelect: (toolId: string) => void;
}

/**
 * Lists every registered tool — active *and* disabled stubs — so the user
 * sees what the system can do today and what's been scoped but not built.
 * Click a tool → opens its inspector entry in the side panel.
 */
export function ToolRegistry({ tools, onSelect }: Props): JSX.Element {
  return (
    <div className="border border-navy-700 rounded-lg bg-navy-800/40 p-4 mb-4">
      <header className="mb-2">
        <h3 className={`${T.heading} text-white flex items-center gap-2`}>
          <Wrench className="w-4 h-4" aria-hidden /> Verfügbare Werkzeuge
        </h3>
        <p className={`${T.body} text-slate-400`}>
          Skills, die der Planner einem Schritt zuordnen kann. Deaktivierte
          Einträge sind dokumentiert, aber nicht implementiert.
        </p>
      </header>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {tools.map((tool) => (
          <li key={tool.name}>
            <button
              type="button"
              onClick={() => onSelect(`tool:${tool.name}`)}
              className={`w-full text-left rounded border px-3 py-2 transition-colors ${
                tool.enabled
                  ? "border-emerald-600 bg-emerald-900/30 hover:bg-emerald-900/50"
                  : "border-zinc-700 bg-zinc-900/30 hover:bg-zinc-900/50 opacity-80"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-white font-semibold">{tool.label}</p>
                <span
                  className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded ${
                    tool.enabled
                      ? "bg-emerald-700 text-emerald-100"
                      : "bg-zinc-700 text-zinc-300"
                  }`}
                >
                  {tool.enabled ? "aktiv" : "stub"}
                </span>
              </div>
              <p className={`${T.tiny} text-slate-300 mt-0.5`}>
                {tool.scope} · {tool.cost_hint} · für{" "}
                {tool.used_by.join(", ") || "—"}
              </p>
              <p className={`${T.tiny} text-slate-400 mt-1 line-clamp-2`}>
                {tool.description}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

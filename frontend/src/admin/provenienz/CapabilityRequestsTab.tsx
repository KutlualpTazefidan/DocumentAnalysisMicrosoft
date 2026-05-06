import { TrendingUp, Wrench } from "lucide-react";

import { useCapabilityRequests } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  token: string;
}

/**
 * "Capability-Wünsche" tab — aggregated TODO list of every
 * capability_request the agent has emitted across all sessions. Sorted
 * by frequency. Powers the data-driven decision of what tool/skill to
 * build next.
 */
export function CapabilityRequestsTab({ token }: Props): JSX.Element {
  const { data, isLoading, error } = useCapabilityRequests(token);

  return (
    <div className="p-4 space-y-3">
      <header>
        <h3 className={`${T.heading} text-white flex items-center gap-2`}>
          <TrendingUp className="w-4 h-4" aria-hidden /> Capability-Wünsche
        </h3>
        <p className={`${T.body} text-slate-400`}>
          Was der Agent während Recherchen anfragt aber nicht hat. Sortiert
          nach Häufigkeit — eine datengestützte TODO-Liste für
          Tool-/Skill-Entwicklung.
        </p>
      </header>

      {isLoading && <p className={`${T.body} text-slate-400`}>Lade…</p>}
      {error && <p className={`${T.body} text-red-400`}>{error.message}</p>}
      {data && data.length === 0 && !isLoading && (
        <p className={`${T.body} text-slate-500 italic`}>
          Noch keine Capability-Wünsche. Sobald der Agent „capability_request" in
          einer Sitzung wählt, erscheint er hier aggregiert.
        </p>
      )}

      <ul className="space-y-2">
        {data?.map((req) => (
          <li
            key={req.name}
            className="rounded border border-yellow-700/40 bg-yellow-900/15 p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Wrench className="w-4 h-4 text-yellow-300 shrink-0" aria-hidden />
                <p className="text-yellow-50 font-semibold font-mono truncate">
                  {req.name}
                </p>
              </div>
              <span className="text-[10px] uppercase tracking-wide bg-yellow-700 text-yellow-50 px-2 py-0.5 rounded shrink-0">
                {req.count}× angefragt
              </span>
            </div>

            {req.examples.length > 0 && (
              <details className="mt-2">
                <summary
                  className={`${T.tiny} text-yellow-300/80 cursor-pointer`}
                >
                  Beispiele ({req.examples.length})
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {req.examples.map((ex) => (
                    <li
                      key={ex.node_id}
                      className="rounded bg-navy-900/60 p-2 border border-navy-700"
                    >
                      <p className={`${T.tiny} text-slate-400 font-mono`}>
                        {ex.slug} · {ex.session_id.slice(0, 12)}… · {ex.created_at}
                      </p>
                      {ex.description && (
                        <p className={`${T.body} text-yellow-100 mt-0.5`}>
                          {ex.description}
                        </p>
                      )}
                      {ex.reasoning && (
                        <p
                          className={`${T.tiny} text-slate-400 italic mt-0.5`}
                        >
                          Begründung: {ex.reasoning}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

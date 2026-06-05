import { useId } from "react";
import { Bot, TrendingUp, UserCog, Wrench } from "lucide-react";

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
  const agentOnlyDescId = useId();
  const allAgentOnly =
    !isLoading &&
    data !== undefined &&
    data.length > 0 &&
    data.every((r) => r.count_by_actor.human === 0);

  return (
    <div className="p-4 space-y-3">
      <header>
        <h3 className={`${T.heading} text-ink flex items-center gap-2`}>
          <TrendingUp className="w-4 h-4" aria-hidden /> Capability-Wünsche
        </h3>
        <p className={`${T.body} text-ink-muted`}>
          Was beim Recherchieren fehlt — vom Agent angefragt oder vom Experten vorgegeben. Sortiert nach Häufigkeit; eine datengestützte TODO-Liste für Tool-/Skill-Entwicklung.
        </p>
      </header>

      {isLoading && <p className={`${T.body} text-ink-muted`}>Lade…</p>}
      {error && <p className={`${T.body} text-red-600`}>{error.message}</p>}
      {data && data.length === 0 && !isLoading && (
        <p className={`${T.body} text-ink-muted italic`}>
          Noch keine Capability-Wünsche. Sobald der Agent eine fehlende Fähigkeit meldet oder ein Experte eine Capability vorgibt, erscheint sie hier aggregiert.
        </p>
      )}

      <span id={agentOnlyDescId} className="sr-only">
        Nur von Agenten angefragt, keine Experten-Vorgabe.
      </span>
      {allAgentOnly && (
        <p
          className={`${T.tiny} text-amber-800 italic mb-2`}
          role="note"
        >
          Noch keine Experten-Vorgaben — Liste zeigt nur Agent-Selbstmeldungen.
        </p>
      )}
      <ul className="space-y-2">
        {data?.map((req) => {
          const isAgentOnly = req.count_by_actor.human === 0;
          const fadeClasses = isAgentOnly
            ? "opacity-50 hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150"
            : "";
          return (
          <li
            key={req.name}
            className={`rounded border border-yellow-200 bg-yellow-50 p-3 ${fadeClasses}`}
            aria-describedby={isAgentOnly ? agentOnlyDescId : undefined}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Wrench className="w-4 h-4 text-yellow-700 shrink-0" aria-hidden />
                <p className="text-yellow-900 font-semibold font-mono truncate">
                  {req.name}
                </p>
              </div>
              <span className="text-[10px] uppercase tracking-wide bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded shrink-0">
                {req.count}× · {req.count_by_actor.human}E / {req.count_by_actor.agent}A
              </span>
            </div>

            {req.examples.length > 0 && (
              <details className="mt-2">
                <summary
                  className={`${T.tiny} text-yellow-700 cursor-pointer`}
                >
                  Beispiele ({req.examples.length})
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {req.examples.map((ex) => (
                    <li
                      key={ex.node_id}
                      className="rounded bg-canvas p-2 border border-line"
                    >
                      <p
                        className={`${T.tiny} text-ink-muted font-mono flex items-center gap-1.5 flex-wrap`}
                      >
                        {ex.actor === "human" ? (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide bg-violet-50 text-violet-800 border border-violet-200 px-1.5 py-0.5 rounded shrink-0"
                            aria-label="Quelle: Experten-Vorgabe"
                            title="Von einem Experten als Capability vorgegeben"
                          >
                            <UserCog className="w-3 h-3" aria-hidden /> Experte
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide bg-sky-50 text-sky-800 border border-sky-200 px-1.5 py-0.5 rounded shrink-0"
                            aria-label="Quelle: Agent-Anfrage"
                            title="Vom Agent während einer Recherche als fehlend gemeldet"
                          >
                            <Bot className="w-3 h-3" aria-hidden /> Agent
                          </span>
                        )}
                        <span>
                          {ex.slug} · {ex.session_id.slice(0, 12)}… · {ex.created_at}
                        </span>
                      </p>
                      {ex.description && (
                        <p className={`${T.body} text-yellow-900 mt-0.5`}>
                          {ex.description}
                        </p>
                      )}
                      {ex.reasoning && (
                        <p
                          className={`${T.tiny} text-ink-muted italic mt-0.5`}
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
          );
        })}
      </ul>
    </div>
  );
}

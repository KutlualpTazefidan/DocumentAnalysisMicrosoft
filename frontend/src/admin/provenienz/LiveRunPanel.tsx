import { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Loader2, X, XCircle } from "lucide-react";

import type { LiveRunPhase, UseNextStepStream } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  run: UseNextStepStream;
  /** Short anchor-text preview shown in the header — usually the first
   *  ~120 chars of the chunk/claim/task that triggered the run. */
  anchorPreview?: string;
  /** Session goal, shown in the header below the anchor. */
  goal?: string;
  /** Called when the user clicks the X — frees the run state for reuse. */
  onClose?: () => void;
}

/**
 * Live view of a /next-step/stream run. Renders one card per phase
 * (gather_guidance, gather_tools, llm_call, validate, persist) with a
 * status icon, elapsed time, and phase-specific payload preview. The
 * llm_call card shows the system-prompt-preview while the LLM is
 * thinking — that is the long phase (~3-5s on Qwen 7B) where live
 * visibility matters most.
 */
export function LiveRunPanel({ run, anchorPreview, goal, onClose }: Props): JSX.Element | null {
  const isVisible =
    run.isRunning || run.phases.length > 0 || run.result !== null || run.error !== null;
  const [tickMs, setTickMs] = useState<number>(0);

  // Tick once per 100ms while running so the elapsed counters update
  // smoothly. Stops as soon as the run completes — no idle timer.
  useEffect(() => {
    if (!run.isRunning || run.startedAt === null) return;
    const start = run.startedAt;
    const id = window.setInterval(() => {
      setTickMs(Date.now() - start);
    }, 100);
    return () => window.clearInterval(id);
  }, [run.isRunning, run.startedAt]);

  if (!isVisible) return null;

  const finalElapsedMs =
    run.startedAt && !run.isRunning && run.phases.length > 0
      ? (run.phases[run.phases.length - 1]?.completedAtMs ?? 0)
      : tickMs;

  return (
    <div className="border border-navy-700 rounded-lg bg-navy-800/40 p-3 space-y-2.5">
      <header className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className={`${T.heading} text-white flex items-center gap-2`}>
            {run.isRunning ? (
              <Loader2 className="w-4 h-4 animate-spin text-blue-400 shrink-0" />
            ) : run.error ? (
              <XCircle className="w-4 h-4 text-red-400 shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            )}
            Live-Lauf · &laquo;Was als nächstes?&raquo;
          </p>
          {anchorPreview && (
            <p className={`${T.tiny} text-slate-400 truncate mt-0.5`} title={anchorPreview}>
              Anker: {anchorPreview}
            </p>
          )}
          {goal && (
            <p className={`${T.tiny} text-slate-400 truncate`} title={goal}>
              Ziel: {goal}
            </p>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-0.5 rounded shrink-0"
            aria-label="Schließen"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </header>

      <RunSummary run={run} />

      <ol className="space-y-1.5">
        {run.phases.map((phase) => (
          <PhaseCard key={phase.phase} phase={phase} tickMs={tickMs} />
        ))}
      </ol>

      {run.error && (
        <div className="rounded border border-red-700 bg-red-950/30 p-2">
          <p className={`${T.tinyBold} text-red-300`}>Fehler</p>
          <p className={`${T.body} text-red-200`}>{run.error}</p>
        </div>
      )}

      <footer className={`${T.tiny} text-slate-500 flex items-center justify-between`}>
        <span>
          {run.phases.length} Phase{run.phases.length === 1 ? "" : "n"}
          {run.result && (
            <>
              {" · "}
              <span className="text-emerald-400">
                Ergebnis: {String(run.result.payload.kind)}
              </span>
            </>
          )}
        </span>
        <span>{(finalElapsedMs / 1000).toFixed(1)}s gesamt</span>
      </footer>
    </div>
  );
}

/**
 * Detect un-substituted ``<placeholder>`` patterns left over from
 * prompt templates the LLM didn't follow. Qwen 3B/7B sometimes
 * leaks them verbatim — we surface that as a soft warning so the
 * user can tighten the corresponding prompt or skill.
 */
const PLACEHOLDER_RE = /<[A-Za-zÄÖÜäöü_][\w\sÄÖÜäöü-]*?>/;
function hasPlaceholderPollution(s: string | null | undefined): boolean {
  return !!s && PLACEHOLDER_RE.test(s);
}

/**
 * Always-on top-of-panel "Decision" block. Shows the final pick + its
 * reasoning prominently so the user doesn't have to scroll through phase
 * cards to see what happened. Surfaces demote info when validate
 * downgraded the LLM's choice.
 */
function RunSummary({ run }: { run: UseNextStepStream }): JSX.Element | null {
  // Pick the most authoritative reasoning available right now.
  // Priority: persisted result → coordinate phase → llm_call phase.
  const result = run.result;
  const coord = run.phases.find((p) => p.phase === "coordinate" && p.status === "completed");
  const llm = run.phases.find((p) => p.phase === "llm_call" && p.status === "completed");
  const validate = run.phases.find(
    (p) => p.phase === "validate" && p.status === "completed",
  );

  const finalKind = result
    ? String(result.payload.kind ?? "")
    : (coord?.payload.kind as string | undefined) ?? "";
  const finalName = result
    ? String(result.payload.name ?? "")
    : (coord?.payload.name as string | undefined) ?? "";
  const finalReasoning = result
    ? String(result.payload.reasoning ?? "")
    : (coord?.payload.reasoning as string | undefined) ??
      (llm?.payload.reasoning as string | undefined) ??
      "";
  // ``description`` carries the human-actionable detail for
  // capability_request / manual_review (and the root cause when the
  // run ended in a parse-error fallback). Pull it from the persisted
  // result — only that node has the field after the persist phase.
  const finalDescription = result
    ? String((result.payload as { description?: unknown }).description ?? "")
    : "";
  const finalGoalAlignment = result
    ? String(result.payload.goal_alignment ?? "")
    : (coord?.payload.goal_alignment as string | undefined) ??
      (llm?.payload.goal_alignment as string | undefined) ??
      "";
  const demotedFrom = validate?.payload.demoted_from
    ? String(validate.payload.demoted_from)
    : null;

  if (!finalKind && !demotedFrom) return null;

  const tone =
    finalKind === "executable_step" || finalKind === "plan_proposal"
      ? "border-emerald-700/60 bg-emerald-950/20"
      : finalKind === "capability_request"
        ? "border-amber-700/60 bg-amber-950/20"
        : finalKind === "manual_review"
          ? "border-rose-700/60 bg-rose-950/20"
          : "border-navy-700 bg-navy-900/40";

  const reasoningHasPollution = hasPlaceholderPollution(finalReasoning);
  const goalHasPollution = hasPlaceholderPollution(finalGoalAlignment);

  return (
    <section className={`rounded border p-2.5 ${tone} space-y-1.5`}>
      <div className="flex items-baseline justify-between gap-2 flex-wrap">
        <p className={T.tinyBold}>Entscheidung</p>
        {demotedFrom && (
          <span className={`${T.tiny} text-amber-300`}>
            ursprünglich <span className="font-mono">{demotedFrom}</span>{" "}
            herabgestuft
          </span>
        )}
      </div>
      {finalKind && (
        <p className={`${T.heading}`}>
          <span className="font-mono text-slate-50">{finalKind}</span>
          {finalName && (
            <>
              <span className="text-slate-500"> / </span>
              <span className="font-mono text-blue-300">{finalName}</span>
            </>
          )}
        </p>
      )}
      {finalReasoning && (
        <div>
          <p className={`${T.body} text-slate-100`}>{finalReasoning}</p>
          {reasoningHasPollution && <PlaceholderWarning />}
        </div>
      )}
      {finalDescription && (
        <div className="rounded bg-navy-950/60 px-2 py-1.5 mt-1">
          <p className={`${T.tiny} text-slate-500 uppercase tracking-wide`}>
            Detail
          </p>
          <p className={`${T.body} text-slate-200 whitespace-pre-wrap break-words`}>
            {finalDescription}
          </p>
        </div>
      )}
      {finalGoalAlignment && (
        <div className="border-l-2 border-pink-700/60 pl-2">
          <p className={`${T.tiny} text-pink-300/80 uppercase tracking-wide`}>
            Ziel-Bezug
          </p>
          <p className={`${T.body} text-pink-100`}>{finalGoalAlignment}</p>
          {goalHasPollution && <PlaceholderWarning />}
        </div>
      )}
    </section>
  );
}

function PlaceholderWarning(): JSX.Element {
  return (
    <p className={`${T.tiny} text-amber-300/90 italic mt-1`}>
      ⚠ Modell hat Template-Platzhalter (<code>{"<...>"}</code>) wörtlich stehen
      lassen — der Skill- oder Prompt-Text ist für Qwen-3B zu komplex. Ersetze
      Platzhalter durch ein konkretes Beispiel.
    </p>
  );
}

function PhaseCard({
  phase,
  tickMs,
}: {
  phase: LiveRunPhase;
  tickMs: number;
}): JSX.Element {
  // Default collapsed: the RunSummary at the top of the panel carries
  // the headline. Phase cards are detail on demand — user clicks to
  // dig in. Status icon + live timer give enough progress signal
  // while running.
  const isLayer2 = phase.phase.startsWith("skill_call:");
  const isLayer3 = phase.phase === "coordinate";
  const [expanded, setExpanded] = useState<boolean>(false);

  const liveMs =
    phase.status === "running" ? Math.max(0, tickMs - phase.startedAtMs) : phase.durationMs ?? 0;

  // Layer-coded backgrounds so the user sees the L1/L2/L3 hierarchy at
  // a glance: blue (running) → emerald (L2 done) → purple (L3 done).
  const borderClass =
    phase.status === "running"
      ? "border-blue-700 bg-blue-950/30"
      : phase.status === "failed"
        ? "border-red-700 bg-red-950/30"
        : isLayer2
          ? "border-emerald-700/60 bg-emerald-950/20"
          : isLayer3
            ? "border-purple-700/60 bg-purple-950/20"
            : "border-navy-700 bg-navy-900/40";

  // Indent L2 cards under their L1 trunk visually.
  const indentClass = isLayer2 ? "ml-3" : "";

  return (
    <li className={`rounded border p-2 ${borderClass} ${indentClass}`}>
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 text-left"
      >
        <StatusIcon status={phase.status} />
        <span className={`${T.body} font-medium text-slate-100 truncate`}>{phase.label}</span>
        <span className={`${T.tiny} text-slate-400 ml-auto shrink-0 tabular-nums`}>
          {(liveMs / 1000).toFixed(1)}s
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        )}
      </button>
      {expanded && (
        <div className="mt-1.5 ml-6">
          <PhasePayload phase={phase} />
          {phase.error && (
            <p className={`${T.tiny} text-red-300 mt-1 italic`}>{phase.error}</p>
          )}
        </div>
      )}
    </li>
  );
}

function StatusIcon({ status }: { status: LiveRunPhase["status"] }): JSX.Element {
  if (status === "running") {
    return <Loader2 className="w-4 h-4 animate-spin text-blue-400 shrink-0" />;
  }
  if (status === "failed") {
    return <XCircle className="w-4 h-4 text-red-400 shrink-0" />;
  }
  return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
}

/**
 * Render the phase-specific payload as a small key/value table. Falls
 * back to a JSON dump for unknown shapes — better than hiding data.
 */
function PhasePayload({ phase }: { phase: LiveRunPhase }): JSX.Element {
  const p = phase.payload;
  // Phase 3 dynamic phase IDs: skill_call:0, skill_call:1, ...
  if (phase.phase.startsWith("skill_call:")) {
    return <SkillCallPayload payload={p} />;
  }
  switch (phase.phase) {
    case "gather_guidance": {
      const guidance = (p.active_guidance ?? []) as Array<{
        kind: string;
        id: string;
        summary: string;
        auto_selected?: boolean;
        selection_reasons?: string[];
      }>;
      const chars = (p.extra_system_chars ?? 0) as number;
      const autoCount = guidance.filter(
        (g) => g.kind === "approach" && g.auto_selected,
      ).length;
      const pinnedCount = guidance.filter(
        (g) => g.kind === "approach" && !g.auto_selected,
      ).length;
      const reasonCount = guidance.filter((g) => g.kind === "reason").length;
      return (
        <div className={`${T.tiny} text-slate-300 space-y-1`}>
          {guidance.length === 0 ? (
            <p className="italic text-slate-500">Keine Heuristiken aktiv für next_step</p>
          ) : (
            <>
              <p className="text-slate-400">
                {pinnedCount > 0 && <>{pinnedCount} gepinnt · </>}
                {autoCount > 0 && (
                  <>
                    <span className="text-emerald-300">{autoCount} auto-gewählt</span>{" "}
                    ·{" "}
                  </>
                )}
                {reasonCount > 0 && <>{reasonCount} Korrektur-Beispiele · </>}
                {chars} Zeichen ins System-Prompt
              </p>
              <ul className="space-y-1">
                {guidance.map((g) => {
                  const isApproach = g.kind === "approach";
                  const isAuto = !!g.auto_selected;
                  return (
                    <li
                      key={`${g.kind}:${g.id}`}
                      className="rounded bg-navy-950/60 px-2 py-1"
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        {isApproach ? (
                          <span
                            className={`px-1.5 py-px rounded text-[10px] font-semibold ${
                              isAuto
                                ? "bg-emerald-700 text-white"
                                : "bg-blue-700 text-white"
                            }`}
                          >
                            {isAuto ? "auto" : "pinned"}
                          </span>
                        ) : (
                          <span className="px-1.5 py-px rounded text-[10px] font-semibold bg-amber-700 text-white">
                            reason
                          </span>
                        )}
                        <span className="font-mono text-slate-200">
                          {g.summary || g.id}
                        </span>
                      </div>
                      {isAuto &&
                        g.selection_reasons &&
                        g.selection_reasons.length > 0 && (
                          <ul className="mt-0.5 ml-4 space-y-0.5">
                            {g.selection_reasons.map((r, i) => (
                              <li
                                key={i}
                                className="text-emerald-200/80 italic before:content-['→_']"
                              >
                                {r}
                              </li>
                            ))}
                          </ul>
                        )}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      );
    }
    case "gather_tools": {
      const steps = (p.available_steps ?? []) as string[];
      const anchorKind = String(p.anchor_kind ?? "?");
      return (
        <div className={`${T.tiny} text-slate-300 space-y-0.5`}>
          <p>
            Anker: <span className="font-mono text-amber-300">{anchorKind}</span>
          </p>
          <p>
            Mögliche Steps:{" "}
            {steps.length === 0 ? (
              <span className="italic text-slate-500">(keine)</span>
            ) : (
              steps.map((s, i) => (
                <span key={s}>
                  <span className="font-mono text-blue-300">{s}</span>
                  {i < steps.length - 1 && <span className="text-slate-500"> · </span>}
                </span>
              ))
            )}
          </p>
        </div>
      );
    }
    case "llm_call": {
      // Anker + Ziel sind schon im Panel-Header — hier nur die LLM-spezifischen
      // Felder zeigen. Reasoning + goal_alignment + Wahl sind in der
      // RunSummary oben prominent — hier nur die LLM-Meta-Daten + Roh-Prompt.
      const sysPreview = String(p.system_prompt_preview ?? "");
      const sysChars = (p.system_prompt_chars ?? 0) as number;
      const model = String(p.model ?? "");
      const kind = p.kind ? String(p.kind) : null;
      const name = p.name ? String(p.name) : null;
      const confidence =
        typeof p.confidence === "number" ? (p.confidence as number) : null;
      return (
        <div className={`${T.tiny} text-slate-300 space-y-1`}>
          {model && (
            <p>
              Modell: <span className="font-mono text-amber-300">{model}</span>
              {sysChars > 0 && (
                <>
                  {" · "}System-Prompt: {sysChars} Zeichen
                </>
              )}
            </p>
          )}
          {kind && (
            <p>
              <span className="text-slate-500">L1-Vorschlag:</span>{" "}
              <span className="font-mono text-emerald-300">{kind}</span>
              {name && (
                <>
                  {" / "}
                  <span className="font-mono text-blue-300">{name}</span>
                </>
              )}
              {confidence !== null && (
                <span className="text-slate-500">
                  {" · "}
                  {(confidence * 100).toFixed(0)}%
                </span>
              )}
            </p>
          )}
          {sysPreview && (
            <details>
              <summary className="cursor-pointer text-slate-500 hover:text-slate-300">
                System-Prompt-Vorschau
              </summary>
              <pre className="mt-1 p-1.5 rounded bg-navy-950 text-[10px] text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                {sysPreview}
              </pre>
            </details>
          )}
        </div>
      );
    }
    case "validate": {
      const ok = p.ok === true;
      const demoted = p.demoted_from ? String(p.demoted_from) : null;
      const finalKind = p.final_kind ? String(p.final_kind) : null;
      const finalName = p.final_name ? String(p.final_name) : null;
      return (
        <div className={`${T.tiny} text-slate-300 space-y-0.5`}>
          {ok ? (
            <p className="text-emerald-300">Step-Wahl in Whitelist ·{" "}
              {finalKind && <span className="font-mono">{finalKind}</span>}
              {finalName && (
                <>
                  {" / "}
                  <span className="font-mono">{finalName}</span>
                </>
              )}
            </p>
          ) : demoted ? (
            <p className="text-amber-300">
              <span className="font-mono">{demoted}</span> nicht in Whitelist - auf{" "}
              <span className="font-mono">manual_review</span> herabgestuft.
            </p>
          ) : (
            <p>{finalKind && <span className="font-mono">{finalKind}</span>}</p>
          )}
        </div>
      );
    }
    case "coordinate": {
      // Finale Wahl + reasoning sind in der RunSummary oben — hier nur der
      // Merge-Vorgang sichtbar machen (was kam rein, wer hat was vorgeschlagen).
      const skillCount = (p.skill_count ?? 0) as number;
      const metaPick = p.meta_pick ? String(p.meta_pick) : null;
      const skillPicks = (p.skill_picks ?? []) as string[];
      const confidence =
        typeof p.confidence === "number" ? (p.confidence as number) : null;
      const kind = p.kind ? String(p.kind) : null;
      return (
        <div className={`${T.tiny} text-slate-300 space-y-0.5`}>
          {metaPick && (
            <p>
              <span className="text-slate-500">Meta-Plan:</span>{" "}
              <span className="font-mono text-blue-300">{metaPick}</span>
            </p>
          )}
          {skillPicks.length > 0 && (
            <p>
              <span className="text-slate-500">Spezialisten:</span>{" "}
              <span className="font-mono text-emerald-300">
                {skillPicks.join(" · ")}
              </span>
            </p>
          )}
          {kind && confidence !== null && (
            <p>
              <span className="text-slate-500">Synthese:</span>{" "}
              <span className="font-mono text-purple-300">{kind}</span>
              <span className="text-slate-500">
                {" · "}
                {(confidence * 100).toFixed(0)}% Konfidenz
              </span>
            </p>
          )}
          {!kind && skillCount > 0 && (
            <p className="text-slate-500 italic">
              Synthesisiere {skillCount} Spezialisten-Stimme(n)...
            </p>
          )}
        </div>
      );
    }
    case "persist": {
      const nodeId = p.node_id ? String(p.node_id) : null;
      const nodeKind = p.node_kind ? String(p.node_kind) : null;
      return (
        <div className={`${T.tiny} text-slate-300`}>
          {nodeId && (
            <p>
              Knoten: <span className="font-mono text-blue-300">{nodeId.slice(0, 12)}...</span>
              {nodeKind && (
                <>
                  {" · "}
                  <span className="font-mono text-amber-300">{nodeKind}</span>
                </>
              )}
            </p>
          )}
        </div>
      );
    }
    default:
      return (
        <pre className={`${T.tiny} text-slate-400 whitespace-pre-wrap`}>
          {JSON.stringify(p, null, 2)}
        </pre>
      );
  }
}

function SkillCallPayload({
  payload,
}: {
  payload: Record<string, unknown>;
}): JSX.Element {
  const approachName = payload.approach_name ? String(payload.approach_name) : "?";
  const preview = payload.approach_extra_system_preview
    ? String(payload.approach_extra_system_preview)
    : "";
  const reasoning = payload.reasoning ? String(payload.reasoning) : null;
  const suggested = payload.suggested_step ? String(payload.suggested_step) : null;
  const confidence =
    typeof payload.confidence === "number" ? (payload.confidence as number) : null;
  return (
    <div className={`${T.tiny} text-slate-300 space-y-1`}>
      <p>
        <span className="text-slate-500">Spezialist:</span>{" "}
        <span className="font-mono text-emerald-300">{approachName}</span>
      </p>
      {reasoning ? (
        <div className="rounded bg-navy-950/60 p-1.5 space-y-1">
          <p className="italic text-slate-200">{reasoning}</p>
          {suggested && (
            <p>
              <span className="text-slate-500">Empfehlung:</span>{" "}
              <span className="font-mono text-blue-300">{suggested}</span>
              {confidence !== null && (
                <span className="text-slate-500">
                  {" · "}
                  {(confidence * 100).toFixed(0)}%
                </span>
              )}
            </p>
          )}
        </div>
      ) : preview ? (
        <details>
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300">
            Spezialwissen-Vorschau
          </summary>
          <pre className="mt-1 p-1.5 rounded bg-navy-950 text-[10px] text-slate-300 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
            {preview}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

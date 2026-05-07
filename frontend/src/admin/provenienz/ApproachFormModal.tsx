import { useEffect, useState } from "react";
import { X } from "lucide-react";

import type {
  ApproachMode,
  ApproachSelectionCriteria,
  ApproachTriggers,
} from "../hooks/useProvenienz";

const VERDICT_OPTIONS = [
  "likely-source",
  "partial-support",
  "unrelated",
  "contradicts",
] as const;
import { T } from "../styles/typography";

const STEP_KIND_OPTIONS = [
  "next_step",
  "extract_claims",
  "extract_claim_background",
  "extract_goal",
  "formulate_task",
  "evaluate",
  "propose_stop",
] as const;

const ANCHOR_KIND_OPTIONS = [
  "chunk",
  "claim",
  "task",
  "search_result",
  "evaluation",
] as const;

const STEP_KIND_HINT: Record<string, string> = {
  next_step:
    "🧠 Beeinflusst, WIE der Agent den nächsten Schritt wählt — Heuristiken zu " +
    "Kapselregeln (capability_request vs. executable_step), Tool-Wahl, " +
    "Eskalations-Kriterien.",
  extract_goal:
    "Beeinflusst die automatische Ableitung des Sitzungs-Ziels aus Chunk + " +
    "erster Aussage.",
  extract_claim_background:
    "🧠 Erweitert den System-Prompt der Aussage-Hintergrund-Extraktion: was " +
    "beim extract_claims-Accept aus dem Chunk pro Aussage als kontextueller " +
    "Background herausgezogen wird (Bezugsgrößen, Voraussetzungen, " +
    "Standort-/Einheits-Info). Standard erzwingt 2-4 Sätze JSON-Array.",
};

export interface ApproachFormValues {
  name: string;
  step_kinds: string[];
  extra_system: string;
  selection_criteria: ApproachSelectionCriteria;
  mode: ApproachMode;
  triggers: ApproachTriggers;
  parent_capability: string;
  domain_rules: string;
}

/** Pretty-print a comma- or newline-separated list of keywords back to
 *  the user, trimmed and de-duped. Suitable for plain words — NOT
 *  regex (which can contain literal commas). */
function parseKeywordList(s: string): string[] {
  return Array.from(
    new Set(
      s
        .split(/[\n,]/)
        .map((x) => x.trim())
        .filter(Boolean),
    ),
  );
}

/** Newline-only splitter for regex patterns. Commas are preserved
 *  because patterns like `\d+[,.]\d+` legitimately contain them. */
function parseRegexList(s: string): string[] {
  return Array.from(
    new Set(
      s
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
    ),
  );
}

function ModeRadio({
  value,
  current,
  onChange,
  label,
  description,
}: {
  value: ApproachMode;
  current: ApproachMode;
  onChange: (v: ApproachMode) => void;
  label: string;
  description: string;
}): JSX.Element {
  const checked = value === current;
  const colour =
    value === "active"
      ? checked
        ? "bg-emerald-700 border-emerald-500 text-white"
        : "bg-navy-800 border-navy-600 text-emerald-300"
      : checked
        ? "bg-blue-700 border-blue-500 text-white"
        : "bg-navy-800 border-navy-600 text-slate-300";
  return (
    <label
      className={`flex-1 cursor-pointer rounded border px-3 py-2 ${colour}`}
    >
      <input
        type="radio"
        className="hidden"
        name="approach-mode"
        checked={checked}
        onChange={() => onChange(value)}
      />
      <div className="flex items-center gap-2">
        <span
          className={`w-3 h-3 rounded-full border ${
            checked ? "bg-white" : "bg-transparent"
          } border-current`}
          aria-hidden
        />
        <span className="font-mono font-semibold">{label}</span>
      </div>
      <p className="text-[11px] opacity-80 mt-1">{description}</p>
    </label>
  );
}

interface Props {
  open: boolean;
  mode: "create" | "edit";
  initialValues: ApproachFormValues;
  /** Used in the modal title in edit mode (e.g. "v3 → v4"). */
  versionPreview?: string;
  /** Called with the final values when the user clicks Save. */
  onSubmit: (values: ApproachFormValues) => void | Promise<void>;
  onClose: () => void;
  /** While the parent's mutation is pending, the Save button shows a spinner
   *  and is disabled. */
  busy?: boolean;
  /** Surface backend errors inside the modal. */
  errorMessage?: string;
}

/**
 * Full-width modal for the entire Approach form (name + step_kinds +
 * prompt body). Replaces the cramped inline form in the side pane.
 *
 * Keyboard:
 *   - Escape           → close (discard)
 *   - Cmd/Ctrl-Enter   → submit
 */
export function ApproachFormModal({
  open,
  mode,
  initialValues,
  versionPreview,
  onSubmit,
  onClose,
  busy = false,
  errorMessage,
}: Props): JSX.Element | null {
  const [name, setName] = useState(initialValues.name);
  const [stepKinds, setStepKinds] = useState<string[]>(initialValues.step_kinds);
  const [text, setText] = useState(initialValues.extra_system);
  const [anchorKinds, setAnchorKinds] = useState<string[]>(
    initialValues.selection_criteria.anchor_kinds ?? [],
  );
  const [goalKeywords, setGoalKeywords] = useState<string>(
    (initialValues.selection_criteria.goal_contains ?? []).join(", "),
  );
  const [textKeywords, setTextKeywords] = useState<string>(
    (initialValues.selection_criteria.text_contains ?? []).join(", "),
  );
  const [approachMode, setApproachMode] = useState<ApproachMode>(
    initialValues.mode ?? "passive",
  );
  const [trigVerdicts, setTrigVerdicts] = useState<string[]>(
    initialValues.triggers?.verdicts ?? [],
  );
  const [trigSentenceRegex, setTrigSentenceRegex] = useState<string>(
    (initialValues.triggers?.sentence_regex ?? []).join("\n"),
  );
  const [trigClaimRegex, setTrigClaimRegex] = useState<string>(
    (initialValues.triggers?.claim_regex ?? []).join("\n"),
  );
  const [trigTopicKeywords, setTrigTopicKeywords] = useState<string>(
    (initialValues.triggers?.topic_keywords ?? []).join(", "),
  );
  const [parentCapability, setParentCapability] = useState<string>(
    initialValues.parent_capability ?? "",
  );
  const [domainRules, setDomainRules] = useState<string>(
    initialValues.domain_rules ?? "",
  );

  useEffect(() => {
    if (open) {
      setName(initialValues.name);
      setStepKinds(initialValues.step_kinds);
      setText(initialValues.extra_system);
      setAnchorKinds(initialValues.selection_criteria.anchor_kinds ?? []);
      setGoalKeywords(
        (initialValues.selection_criteria.goal_contains ?? []).join(", "),
      );
      setTextKeywords(
        (initialValues.selection_criteria.text_contains ?? []).join(", "),
      );
      setApproachMode(initialValues.mode ?? "passive");
      setTrigVerdicts(initialValues.triggers?.verdicts ?? []);
      setTrigSentenceRegex(
        (initialValues.triggers?.sentence_regex ?? []).join("\n"),
      );
      setTrigClaimRegex(
        (initialValues.triggers?.claim_regex ?? []).join("\n"),
      );
      setTrigTopicKeywords(
        (initialValues.triggers?.topic_keywords ?? []).join(", "),
      );
      setParentCapability(initialValues.parent_capability ?? "");
      setDomainRules(initialValues.domain_rules ?? "");
    }
  }, [open, initialValues]);

  const canSubmit = !!(
    name.trim() &&
    stepKinds.length > 0 &&
    (text.trim() || domainRules.trim())
  );

  function buildValues(): ApproachFormValues {
    const goalList = parseKeywordList(goalKeywords);
    const textList = parseKeywordList(textKeywords);
    const criteria: ApproachSelectionCriteria = {};
    if (anchorKinds.length > 0) criteria.anchor_kinds = anchorKinds;
    if (goalList.length > 0) criteria.goal_contains = goalList;
    if (textList.length > 0) criteria.text_contains = textList;
    const sentenceRegex = parseRegexList(trigSentenceRegex);
    const claimRegex = parseRegexList(trigClaimRegex);
    const topicKeywords = parseKeywordList(trigTopicKeywords);
    const triggers: ApproachTriggers = {};
    if (trigVerdicts.length > 0) triggers.verdicts = trigVerdicts;
    if (sentenceRegex.length > 0) triggers.sentence_regex = sentenceRegex;
    if (claimRegex.length > 0) triggers.claim_regex = claimRegex;
    if (topicKeywords.length > 0) triggers.topic_keywords = topicKeywords;
    return {
      name: name.trim(),
      step_kinds: stepKinds,
      extra_system: text.trim(),
      selection_criteria: criteria,
      mode: approachMode,
      triggers,
      parent_capability: parentCapability.trim(),
      domain_rules: domainRules.trim(),
    };
  }

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSubmit && !busy) {
        e.preventDefault();
        void onSubmit(buildValues());
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // buildValues captures all state — re-bind handler when any of them change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    open,
    onClose,
    onSubmit,
    name,
    stepKinds,
    text,
    anchorKinds,
    goalKeywords,
    textKeywords,
    approachMode,
    trigVerdicts,
    trigSentenceRegex,
    trigClaimRegex,
    trigTopicKeywords,
    parentCapability,
    domainRules,
    canSubmit,
    busy,
  ]);

  if (!open) return null;

  const title = mode === "create" ? "Neue Approach anlegen" : `Approach bearbeiten`;
  const hintsToShow = stepKinds.filter((s) => STEP_KIND_HINT[s]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(1100px,95vw)] h-[min(800px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>{title}</h2>
            {(mode === "edit" || versionPreview) && (
              <p className={`${T.tiny} text-slate-400 truncate`}>
                {versionPreview}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
          {/* Name */}
          <div>
            <label
              htmlFor="approach-name"
              className={`${T.tinyBold} block mb-1`}
            >
              Name
            </label>
            <input
              id="approach-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. umgang-chunk"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              autoFocus={mode === "create"}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Eindeutiger Bezeichner — gleicher Name bei späterem Speichern
              bumpt die Version.
            </p>
          </div>

          {/* Step kinds */}
          <div>
            <label className={`${T.tinyBold} block mb-1`}>
              Anwendbar auf Schritte
            </label>
            <div className="flex flex-wrap gap-2">
              {STEP_KIND_OPTIONS.map((s) => {
                const checked = stepKinds.includes(s);
                const isMeta = s === "next_step" || s === "extract_goal";
                return (
                  <label
                    key={s}
                    className={`px-3 py-1.5 rounded cursor-pointer ${T.body} font-mono ${
                      checked
                        ? isMeta
                          ? "bg-amber-700 text-white"
                          : "bg-blue-700 text-white"
                        : isMeta
                          ? "bg-navy-800 text-amber-300 border border-amber-700/40"
                          : "bg-navy-800 text-slate-300 border border-navy-600"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setStepKinds((p) => [...p, s]);
                        else setStepKinds((p) => p.filter((x) => x !== s));
                      }}
                    />
                    {s}
                  </label>
                );
              })}
            </div>
            {hintsToShow.length > 0 && (
              <ul className="mt-2 space-y-1">
                {hintsToShow.map((s) => (
                  <li key={s} className={`${T.tiny} text-amber-300/85 italic`}>
                    {STEP_KIND_HINT[s]}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Mode toggle (Phase 3): passive = Text-Overlay,
              active = eigener Reasoning-Call als Sub-Agent */}
          <div>
            <label className={`${T.tinyBold} block mb-1`}>Modus</label>
            <div className="flex gap-2">
              <ModeRadio
                value="passive"
                current={approachMode}
                onChange={setApproachMode}
                label="passiv"
                description="Text-Overlay im Meta-Planer-Prompt (Standard)"
              />
              <ModeRadio
                value="active"
                current={approachMode}
                onChange={setApproachMode}
                label="aktiv"
                description="Eigener Sub-Agent-Reasoning-Call + Coordinator-Beitrag"
              />
            </div>
            {approachMode === "active" && (
              <p className={`${T.tiny} text-emerald-300/85 italic mt-2`}>
                Bei jedem next_step bekommt diese Approach einen eigenen
                LLM-Call, gibt einen Step-Vorschlag + Begründung zurück, und
                ein Koordinator-LLM merged die Stimmen. Heute nur im
                next_step-Pfad aktiv.
              </p>
            )}
          </div>

          {/* Big prompt body */}
          <div className="flex flex-col flex-1">
            <div className="flex items-center justify-between mb-1">
              <label
                htmlFor="approach-text"
                className={`${T.tinyBold}`}
              >
                System-Prompt-Erweiterung{" "}
                <span className="font-normal text-slate-500">
                  — optional wenn unten Domain-Rules gesetzt sind
                </span>
              </label>
              <span className={`${T.tiny} text-slate-500`}>
                {text.length} Zeichen
              </span>
            </div>
            <textarea
              id="approach-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                "Beispiel:\n\n" +
                "ARBEITSWEISE BEI CHUNK-KNOTEN\n\n" +
                "1. Inhalt vollständig erfassen.\n" +
                "2. Mit Sitzungs-Ziel abgleichen.\n" +
                "3. Nächsten Schritt aus den verfügbaren Steps wählen.\n" +
                "..."
              }
              className="min-h-[280px] w-full p-4 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 text-[14px] leading-relaxed font-mono resize-y"
            />
          </div>

          {/* Auto-Trigger criteria — collapsed by default unless any rule
              already exists. The planner uses these to auto-pin this
              approach when a session anchor + goal match. Empty = no
              auto-trigger. */}
          <details
            className="rounded border border-navy-700 bg-navy-900/40"
            open={
              anchorKinds.length > 0 ||
              goalKeywords.trim().length > 0 ||
              textKeywords.trim().length > 0
            }
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-amber-300`}
            >
              Auto-Trigger (optional) — wann soll diese Approach ohne Pinnen aktiv
              werden?
            </summary>
            <div className="px-3 pb-3 pt-1 space-y-3">
              <p className={`${T.tiny} text-slate-400`}>
                Alle gesetzten Kriterien müssen passen (UND). Innerhalb einer
                Liste reicht ein Treffer (ODER). Leer = nur manuell pinnen.
              </p>

              <div>
                <label className={`${T.tinyBold} block mb-1`}>Anker-Typen</label>
                <div className="flex flex-wrap gap-2">
                  {ANCHOR_KIND_OPTIONS.map((k) => {
                    const checked = anchorKinds.includes(k);
                    return (
                      <label
                        key={k}
                        className={`px-2.5 py-1 rounded cursor-pointer ${T.tiny} font-mono ${
                          checked
                            ? "bg-amber-700 text-white"
                            : "bg-navy-800 text-slate-300 border border-navy-600"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="hidden"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setAnchorKinds((p) => [...p, k]);
                            } else {
                              setAnchorKinds((p) => p.filter((x) => x !== k));
                            }
                          }}
                        />
                        {k}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <label
                  htmlFor="approach-goal-keywords"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Ziel enthält (Keywords, Komma-getrennt)
                </label>
                <input
                  id="approach-goal-keywords"
                  type="text"
                  value={goalKeywords}
                  onChange={(e) => setGoalKeywords(e.target.value)}
                  placeholder="z.B. Beleg, prüfen, verifizieren"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
                />
              </div>

              <div>
                <label
                  htmlFor="approach-text-keywords"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Anker-Text enthält (Keywords, Komma-getrennt)
                </label>
                <input
                  id="approach-text-keywords"
                  type="text"
                  value={textKeywords}
                  onChange={(e) => setTextKeywords(e.target.value)}
                  placeholder="z.B. kW, MW, °C"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
                />
              </div>
            </div>
          </details>

          {/* Reactive-Capability Layer — Trigger + Hierarchie + Domain-Rules */}
          <details
            className="rounded border border-orange-700/40 bg-orange-950/10"
            open={
              trigVerdicts.length > 0 ||
              trigSentenceRegex.trim().length > 0 ||
              trigClaimRegex.trim().length > 0 ||
              trigTopicKeywords.trim().length > 0 ||
              parentCapability.length > 0 ||
              domainRules.length > 0
            }
          >
            <summary className={`${T.tinyBold} cursor-pointer px-3 py-2 text-orange-300`}>
              🔧 Reactive Capability (optional) — Domain-Wissen das nach
              evaluate via Trigger geladen wird
            </summary>
            <div className="px-3 pb-3 pt-1 space-y-3">
              <p className={`${T.tiny} text-slate-400`}>
                Wenn ALLE gesetzten Trigger matchen (UND-Logik), wird diese
                Capability nach jeder evaluate-Aktion automatisch erkannt
                und als ladbare Domain-Expertise angeboten.
              </p>

              <div>
                <label className={`${T.tinyBold} block mb-1`}>
                  Triggert nur bei diesen Verdicts
                </label>
                <div className="flex flex-wrap gap-2">
                  {VERDICT_OPTIONS.map((v) => {
                    const checked = trigVerdicts.includes(v);
                    return (
                      <label
                        key={v}
                        className={`px-2.5 py-1 rounded cursor-pointer ${T.tiny} font-mono ${
                          checked
                            ? "bg-orange-700 text-white"
                            : "bg-navy-800 text-slate-300 border border-navy-600"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="hidden"
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setTrigVerdicts((p) => [...p, v]);
                            } else {
                              setTrigVerdicts((p) => p.filter((x) => x !== v));
                            }
                          }}
                        />
                        {v}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <label
                  htmlFor="approach-trig-sentence"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Satz-Regex{" "}
                  <span className="font-normal text-slate-500">
                    (eine Regex pro Zeile — Kommas erlaubt!)
                  </span>
                </label>
                <textarea
                  id="approach-trig-sentence"
                  value={trigSentenceRegex}
                  onChange={(e) => setTrigSentenceRegex(e.target.value)}
                  rows={2}
                  placeholder={String.raw`\d+[,.]\d+\s*(kW|MW|MPa)`}
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body} resize-y`}
                />
              </div>

              <div>
                <label
                  htmlFor="approach-trig-claim"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Claim-Regex{" "}
                  <span className="font-normal text-slate-500">
                    (eine Regex pro Zeile)
                  </span>
                </label>
                <textarea
                  id="approach-trig-claim"
                  value={trigClaimRegex}
                  onChange={(e) => setTrigClaimRegex(e.target.value)}
                  rows={2}
                  placeholder="Wärmeleistung\nNachzerfall"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body} resize-y`}
                />
              </div>

              <div>
                <label
                  htmlFor="approach-trig-topic"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Topic-Keywords (Komma-getrennt, OR-match)
                </label>
                <input
                  id="approach-trig-topic"
                  type="text"
                  value={trigTopicKeywords}
                  onChange={(e) => setTrigTopicKeywords(e.target.value)}
                  placeholder="z.B. Nachzerfallsleistung, Wärmeleistung, thermisch"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 ${T.body}`}
                />
              </div>

              <div>
                <label
                  htmlFor="approach-parent"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Parent-Capability (leer = top-level)
                </label>
                <input
                  id="approach-parent"
                  type="text"
                  value={parentCapability}
                  onChange={(e) => setParentCapability(e.target.value)}
                  placeholder="z.B. compare_numbers"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body}`}
                />
                <p className={`${T.tiny} text-slate-500 mt-1`}>
                  Sub-Skill: wird nur geladen wenn der genannte Parent
                  feuert UND die eigenen Trigger matchen.
                </p>
              </div>

              <div>
                <label
                  htmlFor="approach-domain-rules"
                  className={`${T.tinyBold} block mb-1`}
                >
                  Domain-Rules (in re_evaluate-Prompt injiziert)
                </label>
                <textarea
                  id="approach-domain-rules"
                  value={domainRules}
                  onChange={(e) => setDomainRules(e.target.value)}
                  rows={6}
                  placeholder={
                    "WICHTIG bei Wärmeleistung:\n" +
                    "- Aufrundung der angegebenen Zahl ist OFT KONSERVATIV\n" +
                    "- Beispiel: angegeben 5,6 kW, tatsächlich 5,597 kW → STÜTZT"
                  }
                  className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 ${T.body} font-mono resize-y`}
                />
              </div>
            </div>
          </details>

          {errorMessage && (
            <p className={`${T.body} text-red-400`}>{errorMessage}</p>
          )}
        </div>

        <footer className="px-4 py-3 border-t border-navy-700 flex items-center justify-between">
          <span className={`${T.tiny} text-slate-500`}>
            Cmd/Ctrl-Enter zum Speichern · Esc zum Abbrechen
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className={`px-3 py-1.5 rounded text-slate-300 hover:bg-navy-700 ${T.body}`}
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={() => void onSubmit(buildValues())}
              disabled={!canSubmit || busy}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold disabled:opacity-50`}
            >
              {busy
                ? mode === "create"
                  ? "Erstelle…"
                  : "Speichere…"
                : mode === "create"
                  ? "Erstellen"
                  : "Speichern"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

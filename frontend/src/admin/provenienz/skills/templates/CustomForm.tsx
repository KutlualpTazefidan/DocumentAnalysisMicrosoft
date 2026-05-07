import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useToast } from "../../../../shared/components/useToast";
import {
  useCreateSkill,
  type CreateSkillRequest,
  type SkillKind,
  type TriggerConditions,
} from "../../../hooks/useSkills";
import { T } from "../../../styles/typography";

interface CustomFormProps {
  open: boolean;
  onClose: () => void;
  token: string;
}

// ----- option pools ------------------------------------------------------

const SKILL_KIND_OPTIONS: {
  value: SkillKind;
  label: string;
  description: string;
}[] = [
  {
    value: "enrichment",
    label: "enrichment",
    description: "Reichert Aussagen mit zusätzlichen Infos aus dem Chunk an.",
  },
  {
    value: "prompt-overlay",
    label: "prompt-overlay",
    description: "Erweitert den System-Prompt eines Schritts um freien Text.",
  },
  {
    value: "reactive",
    label: "reactive",
    description: "Greift nach evaluate ein, wenn Trigger-Bedingungen passen.",
  },
  {
    value: "note",
    label: "note",
    description: "Lehr-Notiz / Kommentar — wird ohne Aktion mitgeführt.",
  },
  {
    value: "subagent",
    label: "subagent",
    description: "Eigener Sub-Agent mit eigenem Reasoning-Call.",
  },
];

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

const VERDICT_OPTIONS = [
  "likely-source",
  "partial-support",
  "unrelated",
  "contradicts",
] as const;

// ----- parsing helpers ---------------------------------------------------

/** Split a comma-or-newline-separated keyword list. Trims, drops empties + dupes. */
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

/** Newline-only splitter (regex / questions — commas are content, not separators). */
function parseLines(s: string): string[] {
  return Array.from(
    new Set(
      s
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
    ),
  );
}

const EMPTY_CONDITIONS: TriggerConditions = {
  verdicts: [],
  sentence_regex: [],
  claim_regex: [],
  topic_keywords: [],
  anchor_kinds: [],
  goal_contains: [],
  text_contains: [],
};

/**
 * CustomForm — power-user template, ALL Skill fields exposed.
 *
 * The five preset templates (Enrichment / PromptOverlay / Reactive / Note /
 * AgentRule) cover ~95% of cases with hidden defaults; this form is the
 * escape hatch for cases none of them fit. Sections are always rendered,
 * with a grey "(nur relevant für …)" hint where a field only matters for
 * a specific `skill_kind` — backend validation rejects nonsense
 * combinations.
 */
export function CustomForm({
  open,
  onClose,
  token,
}: CustomFormProps): JSX.Element | null {
  // Basis
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [skillKind, setSkillKind] = useState<SkillKind>("enrichment");

  // Wann (fires_on)
  const [firesOn, setFiresOn] = useState<string[]>([]);

  // Prompt
  const [freeText, setFreeText] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [domainRules, setDomainRules] = useState("");

  // Bedingungen (TriggerConditions)
  const [verdicts, setVerdicts] = useState<string[]>([]);
  const [sentenceRegexText, setSentenceRegexText] = useState("");
  const [claimRegexText, setClaimRegexText] = useState("");
  const [topicKeywords, setTopicKeywords] = useState("");
  const [anchorKinds, setAnchorKinds] = useState<string[]>([]);
  const [goalContains, setGoalContains] = useState("");
  const [textContains, setTextContains] = useState("");

  // Output (Annotation)
  const [annotationKind, setAnnotationKind] = useState("");
  const [attachesTo, setAttachesTo] = useState("");
  const [consumedBy, setConsumedBy] = useState("");

  // Hierarchie
  const [parentSkill, setParentSkill] = useState("");

  const createMutation = useCreateSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();

  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setEnabled(true);
      setSkillKind("enrichment");
      setFiresOn([]);
      setFreeText("");
      setQuestionsText("");
      setDomainRules("");
      setVerdicts([]);
      setSentenceRegexText("");
      setClaimRegexText("");
      setTopicKeywords("");
      setAnchorKinds([]);
      setGoalContains("");
      setTextContains("");
      setAnnotationKind("");
      setAttachesTo("");
      setConsumedBy("");
      setParentSkill("");
      createMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function toggleIn(list: string[], v: string): string[] {
    return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  }

  const questions = parseLines(questionsText);
  const sentenceRegex = parseLines(sentenceRegexText);
  const claimRegex = parseLines(claimRegexText);
  const topicList = parseKeywordList(topicKeywords);
  const goalList = parseKeywordList(goalContains);
  const textList = parseKeywordList(textContains);
  const consumedList = parseKeywordList(consumedBy);

  // Minimum: Name + at least one fires_on. The backend kind-specific
  // validators handle the deeper checks (e.g. enrichment requires output).
  const canSubmit = !!name.trim() && firesOn.length > 0;

  function buildSkill(): CreateSkillRequest {
    return {
      name: name.trim(),
      skill_kind: skillKind,
      fires_on: firesOn,
      conditions: {
        ...EMPTY_CONDITIONS,
        verdicts,
        sentence_regex: sentenceRegex,
        claim_regex: claimRegex,
        topic_keywords: topicList,
        anchor_kinds: anchorKinds,
        goal_contains: goalList,
        text_contains: textList,
      },
      parent_skill: parentSkill.trim(),
      prompt: {
        free_text: freeText.trim(),
        questions,
        domain_rules: domainRules.trim(),
      },
      output: {
        annotation_kind: annotationKind.trim(),
        attaches_to: attachesTo.trim(),
        consumed_by: consumedList,
      },
      description: description.trim(),
      enabled,
    };
  }

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    try {
      await createMutation.mutateAsync(buildSkill());
      toastSuccess(`Skill "${name.trim()}" erstellt.`);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler beim Erstellen");
    }
  }

  // ESC closes; Cmd/Ctrl-Enter submits.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (
        e.key === "Enter" &&
        (e.metaKey || e.ctrlKey) &&
        canSubmit &&
        !createMutation.isPending
      ) {
        e.preventDefault();
        void handleSubmit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    open,
    canSubmit,
    createMutation.isPending,
    name,
    description,
    enabled,
    skillKind,
    firesOn,
    freeText,
    questionsText,
    domainRules,
    verdicts,
    sentenceRegexText,
    claimRegexText,
    topicKeywords,
    anchorKinds,
    goalContains,
    textContains,
    annotationKind,
    attachesTo,
    consumedBy,
    parentSkill,
  ]);

  if (!open) return null;

  const previewSkill = buildSkill();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Eigener Skill"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(1100px,95vw)] h-[min(880px,92vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>
              Eigener Skill
            </h2>
            <p className={`${T.tiny} text-slate-400`}>
              Volle Kontrolle — alle Felder sichtbar. Backend validiert
              kind-spezifisch.
            </p>
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
          {/* ----- Basis ---------------------------------------------- */}
          <Section title="Basis">
            <div>
              <label
                htmlFor="custom-name"
                className={`${T.tinyBold} block mb-1`}
              >
                Name
              </label>
              <input
                id="custom-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. mein-skill"
                className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
                autoFocus
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Eindeutiger Bezeichner — gleicher Name bumpt die Version beim
                Speichern.
              </p>
            </div>

            <div>
              <label
                htmlFor="custom-description"
                className={`${T.tinyBold} block mb-1`}
              >
                Beschreibung
              </label>
              <input
                id="custom-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Einzeiler — wofür ist dieser Skill da?"
                className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              />
            </div>

            <div>
              <label className={`${T.tinyBold} block mb-1`}>Aktiviert</label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="accent-blue-500"
                />
                <span className={`${T.body} text-slate-300`}>
                  {enabled ? "aktiv" : "inaktiv"}
                </span>
              </label>
            </div>

            <div>
              <label
                htmlFor="custom-skill-kind"
                className={`${T.tinyBold} block mb-1`}
              >
                skill_kind
              </label>
              <select
                id="custom-skill-kind"
                value={skillKind}
                onChange={(e) => setSkillKind(e.target.value as SkillKind)}
                className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 ${T.body} font-mono`}
              >
                {SKILL_KIND_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                {SKILL_KIND_OPTIONS.find((o) => o.value === skillKind)
                  ?.description ?? ""}
              </p>
            </div>
          </Section>

          {/* ----- Wann (fires_on) ----------------------------------- */}
          <Section title="Wann (fires_on)">
            <div>
              <label className={`${T.tinyBold} block mb-1`}>
                Anwendbar auf Schritte
              </label>
              <div className="flex flex-wrap gap-2">
                {STEP_KIND_OPTIONS.map((s) => {
                  const checked = firesOn.includes(s);
                  return (
                    <label
                      key={s}
                      className={`px-3 py-1.5 rounded cursor-pointer ${T.body} font-mono ${
                        checked
                          ? "bg-blue-700 text-white"
                          : "bg-navy-800 text-slate-300 border border-navy-600"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="hidden"
                        checked={checked}
                        onChange={() =>
                          setFiresOn((cur) => toggleIn(cur, s))
                        }
                      />
                      {s}
                    </label>
                  );
                })}
              </div>
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Mindestens einen Schritt wählen — sonst feuert der Skill nie.
              </p>
            </div>
          </Section>

          {/* ----- Prompt -------------------------------------------- */}
          <Section title="Prompt">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label
                  htmlFor="custom-free-text"
                  className={`${T.tinyBold}`}
                >
                  free_text{" "}
                  <span className="font-normal text-slate-500">
                    (System-Prompt-Erweiterung — primär für prompt-overlay /
                    subagent / note)
                  </span>
                </label>
                <span className={`${T.tiny} text-slate-500`}>
                  {freeText.length} Zeichen
                </span>
              </div>
              <textarea
                id="custom-free-text"
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                rows={6}
                placeholder={
                  "Beispiel:\n\n" +
                  "ARBEITSWEISE BEI CHUNK-KNOTEN\n" +
                  "1. Inhalt vollständig erfassen.\n" +
                  "2. Mit Sitzungs-Ziel abgleichen.\n" +
                  "..."
                }
                className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
              />
            </div>

            <div>
              <label
                htmlFor="custom-questions"
                className={`${T.tinyBold} block mb-1`}
              >
                questions{" "}
                <span className="font-normal text-slate-500">
                  (eine Frage pro Zeile — nur relevant für enrichment)
                </span>
              </label>
              <textarea
                id="custom-questions"
                value={questionsText}
                onChange={(e) => setQuestionsText(e.target.value)}
                rows={6}
                placeholder={
                  "Welcher Reaktor-Typ ist gemeint?\n" +
                  "Welche Werte-Klasse ist anwendbar?\n" +
                  "Standort / Anlage?"
                }
                className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                {questions.length} Frage(n) erkannt.
              </p>
            </div>

            <div>
              <label
                htmlFor="custom-domain-rules"
                className={`${T.tinyBold} block mb-1`}
              >
                domain_rules{" "}
                <span className="font-normal text-slate-500">
                  (in re_evaluate-Prompt injiziert — nur relevant für
                  reactive)
                </span>
              </label>
              <textarea
                id="custom-domain-rules"
                value={domainRules}
                onChange={(e) => setDomainRules(e.target.value)}
                rows={6}
                placeholder={
                  "WICHTIG bei Wärmeleistung:\n" +
                  "- Aufrundung der angegebenen Zahl ist OFT KONSERVATIV\n" +
                  "- Beispiel: angegeben 5,6 kW, tatsächlich 5,597 kW → STÜTZT"
                }
                className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
              />
            </div>
          </Section>

          {/* ----- Bedingungen (TriggerConditions) -------------------- */}
          <details className="rounded border border-navy-700 bg-navy-900/40">
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-amber-300`}
            >
              Bedingungen (TriggerConditions) — UND zwischen Feldern, ODER
              innerhalb einer Liste
            </summary>
            <div className="px-3 pb-3 pt-1 space-y-3">
              {/* verdicts */}
              <div>
                <label className={`${T.tinyBold} block mb-1`}>
                  verdicts{" "}
                  <span className="font-normal text-slate-500">
                    (nur relevant für reactive)
                  </span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {VERDICT_OPTIONS.map((v) => {
                    const checked = verdicts.includes(v);
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
                          onChange={() =>
                            setVerdicts((cur) => toggleIn(cur, v))
                          }
                        />
                        {v}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* sentence_regex */}
              <div>
                <label
                  htmlFor="custom-sentence-regex"
                  className={`${T.tinyBold} block mb-1`}
                >
                  sentence_regex{" "}
                  <span className="font-normal text-slate-500">
                    (eine Regex pro Zeile — Kommas erlaubt)
                  </span>
                </label>
                <textarea
                  id="custom-sentence-regex"
                  value={sentenceRegexText}
                  onChange={(e) => setSentenceRegexText(e.target.value)}
                  rows={2}
                  placeholder={String.raw`\d+[,.]\d+\s*(kW|MW|MPa)`}
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body} resize-y`}
                />
              </div>

              {/* claim_regex */}
              <div>
                <label
                  htmlFor="custom-claim-regex"
                  className={`${T.tinyBold} block mb-1`}
                >
                  claim_regex{" "}
                  <span className="font-normal text-slate-500">
                    (eine Regex pro Zeile)
                  </span>
                </label>
                <textarea
                  id="custom-claim-regex"
                  value={claimRegexText}
                  onChange={(e) => setClaimRegexText(e.target.value)}
                  rows={2}
                  placeholder={"Wärmeleistung\nNachzerfall"}
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body} resize-y`}
                />
              </div>

              {/* topic_keywords */}
              <div>
                <label
                  htmlFor="custom-topic-keywords"
                  className={`${T.tinyBold} block mb-1`}
                >
                  topic_keywords (Komma-getrennt, OR-match)
                </label>
                <input
                  id="custom-topic-keywords"
                  type="text"
                  value={topicKeywords}
                  onChange={(e) => setTopicKeywords(e.target.value)}
                  placeholder="z.B. Nachzerfallsleistung, Wärmeleistung, thermisch"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 ${T.body}`}
                />
              </div>

              {/* anchor_kinds */}
              <div>
                <label className={`${T.tinyBold} block mb-1`}>
                  anchor_kinds
                </label>
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
                          onChange={() =>
                            setAnchorKinds((cur) => toggleIn(cur, k))
                          }
                        />
                        {k}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* goal_contains */}
              <div>
                <label
                  htmlFor="custom-goal-contains"
                  className={`${T.tinyBold} block mb-1`}
                >
                  goal_contains (Komma-getrennt)
                </label>
                <input
                  id="custom-goal-contains"
                  type="text"
                  value={goalContains}
                  onChange={(e) => setGoalContains(e.target.value)}
                  placeholder="z.B. Beleg, prüfen, verifizieren"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 ${T.body}`}
                />
              </div>

              {/* text_contains */}
              <div>
                <label
                  htmlFor="custom-text-contains"
                  className={`${T.tinyBold} block mb-1`}
                >
                  text_contains (Komma-getrennt)
                </label>
                <input
                  id="custom-text-contains"
                  type="text"
                  value={textContains}
                  onChange={(e) => setTextContains(e.target.value)}
                  placeholder="z.B. kW, MW, °C"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 ${T.body}`}
                />
              </div>
            </div>
          </details>

          {/* ----- Output (Annotation) -------------------------------- */}
          <details className="rounded border border-navy-700 bg-navy-900/40">
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-cyan-300`}
            >
              Output (Annotation){" "}
              <span className="font-normal text-slate-500">
                — nur relevant für enrichment
              </span>
            </summary>
            <div className="px-3 pb-3 pt-1 space-y-3">
              <div>
                <label
                  htmlFor="custom-annotation-kind"
                  className={`${T.tinyBold} block mb-1`}
                >
                  annotation_kind
                </label>
                <input
                  id="custom-annotation-kind"
                  type="text"
                  value={annotationKind}
                  onChange={(e) => setAnnotationKind(e.target.value)}
                  placeholder="z.B. claim_background"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body}`}
                />
              </div>

              <div>
                <label
                  htmlFor="custom-attaches-to"
                  className={`${T.tinyBold} block mb-1`}
                >
                  attaches_to
                </label>
                <input
                  id="custom-attaches-to"
                  type="text"
                  value={attachesTo}
                  onChange={(e) => setAttachesTo(e.target.value)}
                  placeholder="z.B. claim"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body}`}
                />
              </div>

              <div>
                <label
                  htmlFor="custom-consumed-by"
                  className={`${T.tinyBold} block mb-1`}
                >
                  consumed_by (Komma-getrennt)
                </label>
                <input
                  id="custom-consumed-by"
                  type="text"
                  value={consumedBy}
                  onChange={(e) => setConsumedBy(e.target.value)}
                  placeholder="z.B. formulate_task, evaluate"
                  className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body}`}
                />
              </div>
            </div>
          </details>

          {/* ----- Hierarchie ---------------------------------------- */}
          <Section title="Hierarchie">
            <div>
              <label
                htmlFor="custom-parent-skill"
                className={`${T.tinyBold} block mb-1`}
              >
                parent_skill (Skill-ID oder -Name)
              </label>
              <input
                id="custom-parent-skill"
                type="text"
                value={parentSkill}
                onChange={(e) => setParentSkill(e.target.value)}
                placeholder="z.B. compare-numbers"
                className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 font-mono ${T.body}`}
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Sub-Skill: wird nur geladen wenn der genannte Parent feuert UND
                die eigenen Trigger matchen. Leer = top-level.
              </p>
            </div>
          </Section>

          {/* ----- Roh-Daten ----------------------------------------- */}
          <details className="rounded border border-navy-700 bg-navy-900/30">
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-slate-400`}
            >
              Roh-Daten anzeigen
            </summary>
            <pre
              className={`px-3 pb-3 pt-1 ${T.tiny} text-slate-300 font-mono whitespace-pre-wrap break-all`}
            >
              {JSON.stringify(previewSkill, null, 2)}
            </pre>
          </details>

          {!canSubmit && (name.trim() || firesOn.length > 0) && (
            <p className={`${T.tiny} text-amber-300`}>
              {!name.trim() && "Name ist Pflicht. "}
              {firesOn.length === 0 && "Mindestens ein fires_on-Schritt wählen."}
            </p>
          )}

          {createMutation.error && (
            <p className={`${T.body} text-red-400`}>
              {createMutation.error.message}
            </p>
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
              onClick={() => void handleSubmit()}
              disabled={!canSubmit || createMutation.isPending}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold disabled:opacity-50`}
            >
              {createMutation.isPending ? "Erstelle…" : "Erstellen"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------
// Internal: bordered group with a header label, used to give every section
// the same visual language.
// -------------------------------------------------------------------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <fieldset className="rounded border border-navy-700 bg-navy-900/30 px-3 pt-2 pb-3 space-y-3">
      <legend className={`${T.tinyBold} text-slate-200 px-1`}>{title}</legend>
      {children}
    </fieldset>
  );
}

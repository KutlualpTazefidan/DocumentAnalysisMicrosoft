import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useToast } from "../../../../shared/components/useToast";
import {
  useCreateSkill,
  type CreateSkillRequest,
  type TriggerConditions,
} from "../../../hooks/useSkills";
import { T } from "../../../styles/typography";

interface ReactiveFormProps {
  open: boolean;
  onClose: () => void;
  token: string;
}

const VERDICT_OPTIONS: { value: string; label: string }[] = [
  { value: "likely-source", label: "likely-source" },
  { value: "partial-support", label: "partial-support" },
  { value: "unrelated", label: "unrelated" },
  { value: "contradicts", label: "contradicts" },
];

/** Split textarea content into one trimmed line per row, dropping empties. */
function parseLines(s: string): string[] {
  return s
    .split("\n")
    .map((q) => q.trim())
    .filter(Boolean);
}

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
 * ReactiveForm — template "⚖ Bewertung neu fassen".
 *
 * The most-detailed template (5+ visible fields) since reactive skills
 * need a precise trigger filter on top of a domain-rule. Hidden defaults:
 * skill_kind=reactive, fires_on=[evaluate], free_text="" (Domain-Regel
 * lebt in prompt.domain_rules, nicht in free_text).
 */
export function ReactiveForm({
  open,
  onClose,
  token,
}: ReactiveFormProps): JSX.Element | null {
  const [name, setName] = useState("");
  const [verdicts, setVerdicts] = useState<string[]>([]);
  const [claimRegexText, setClaimRegexText] = useState("");
  const [sentenceRegexText, setSentenceRegexText] = useState("");
  const [topicKeywords, setTopicKeywords] = useState("");
  const [domainRules, setDomainRules] = useState("");
  const [parentSkill, setParentSkill] = useState("");
  const createMutation = useCreateSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();

  useEffect(() => {
    if (open) {
      setName("");
      setVerdicts([]);
      setClaimRegexText("");
      setSentenceRegexText("");
      setTopicKeywords("");
      setDomainRules("");
      setParentSkill("");
      createMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function toggleVerdict(v: string): void {
    setVerdicts((cur) =>
      cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v],
    );
  }

  const claimRegex = parseLines(claimRegexText);
  const sentenceRegex = parseLines(sentenceRegexText);
  const topicList = parseKeywordList(topicKeywords);
  const hasTrigger =
    verdicts.length > 0 ||
    claimRegex.length > 0 ||
    sentenceRegex.length > 0 ||
    topicList.length > 0;
  const canSubmit = !!name.trim() && hasTrigger && !!domainRules.trim();

  function buildSkill(): CreateSkillRequest {
    return {
      name: name.trim(),
      skill_kind: "reactive",
      fires_on: ["evaluate"],
      conditions: {
        ...EMPTY_CONDITIONS,
        verdicts,
        claim_regex: claimRegex,
        sentence_regex: sentenceRegex,
        topic_keywords: topicList,
      },
      parent_skill: parentSkill.trim(),
      prompt: {
        free_text: "",
        questions: [],
        domain_rules: domainRules.trim(),
      },
      output: { annotation_kind: "", attaches_to: "", consumed_by: [] },
      description: "",
      enabled: true,
    };
  }

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    try {
      await createMutation.mutateAsync(buildSkill());
      toastSuccess(`Fähigkeit "${name.trim()}" erstellt.`);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler beim Erstellen");
    }
  }

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
    verdicts,
    claimRegexText,
    sentenceRegexText,
    topicKeywords,
    domainRules,
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
        aria-label="Bewertung neu fassen"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(820px,95vw)] h-[min(820px,92vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>
              ⚖ Bewertung neu fassen
            </h2>
            <p className={`${T.tiny} text-slate-400`}>
              Reagiert auf bestimmte Verdicts und wendet Domain-Wissen an.
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
          {/* Name */}
          <div>
            <label htmlFor="reactive-name" className={`${T.tinyBold} block mb-1`}>
              Name
            </label>
            <input
              id="reactive-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. compare-numbers"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              autoFocus
            />
          </div>

          {/* Verdicts */}
          <div>
            <label className={`${T.tinyBold} block mb-1`}>
              Wann soll die Fähigkeit reagieren? (Verdicts)
            </label>
            <div className="flex flex-wrap gap-2">
              {VERDICT_OPTIONS.map((opt) => {
                const selected = verdicts.includes(opt.value);
                return (
                  <button
                    type="button"
                    key={opt.value}
                    onClick={() => toggleVerdict(opt.value)}
                    className={`px-2.5 py-1 rounded ${T.tiny} border transition-colors ${
                      selected
                        ? "bg-orange-700 border-orange-500 text-white"
                        : "bg-navy-900 border-navy-600 text-slate-300 hover:border-orange-400"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Mehrfach-Auswahl möglich. Leer = Verdict ist kein Trigger.
            </p>
          </div>

          {/* Claim regex */}
          <div>
            <label
              htmlFor="reactive-claim-regex"
              className={`${T.tinyBold} block mb-1`}
            >
              Aussage erwähnt (claim_regex, eine Regex pro Zeile)
            </label>
            <textarea
              id="reactive-claim-regex"
              value={claimRegexText}
              onChange={(e) => setClaimRegexText(e.target.value)}
              rows={3}
              placeholder={"\\d+\\s*MW\n(?i)nachzerfallsleistung"}
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              {claimRegex.length} Regex(es) erkannt.
            </p>
          </div>

          {/* Sentence regex */}
          <div>
            <label
              htmlFor="reactive-sentence-regex"
              className={`${T.tinyBold} block mb-1`}
            >
              Treffer enthält Regex (sentence_regex, eine pro Zeile)
            </label>
            <textarea
              id="reactive-sentence-regex"
              value={sentenceRegexText}
              onChange={(e) => setSentenceRegexText(e.target.value)}
              rows={3}
              placeholder={"\\d+\\s*MW\n(?i)\\babklingen\\b"}
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              {sentenceRegex.length} Regex(es) erkannt.
            </p>
          </div>

          {/* Topic keywords */}
          <div>
            <label
              htmlFor="reactive-topic-keywords"
              className={`${T.tinyBold} block mb-1`}
            >
              Sitzungs-Topic enthält (Keywords, Komma-getrennt)
            </label>
            <input
              id="reactive-topic-keywords"
              type="text"
              value={topicKeywords}
              onChange={(e) => setTopicKeywords(e.target.value)}
              placeholder="z.B. nachzerfallswärme, restwärme"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
            />
          </div>

          {/* Domain rules — required */}
          <div>
            <label
              htmlFor="reactive-domain-rules"
              className={`${T.tinyBold} block mb-1`}
            >
              Welche Domain-Regel? (wird in evaluate-Prompt eingespielt)
            </label>
            <textarea
              id="reactive-domain-rules"
              value={domainRules}
              onChange={(e) => setDomainRules(e.target.value)}
              rows={6}
              placeholder={
                "Beispiel:\n\n" +
                "Wenn Aussage und Treffer Zahlenwerte mit unterschiedlichen " +
                "Einheiten enthalten, prüfe explizit die Umrechnung. " +
                "Toleranz ±2% bei MW-zu-MW-Vergleichen."
              }
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Pflicht — die Regel, die der Agent bei der Re-Evaluation anwendet.
            </p>
          </div>

          {/* Parent skill (optional, collapsed) */}
          <details
            className="rounded border border-navy-700 bg-navy-900/40"
            open={parentSkill.trim().length > 0}
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-amber-300`}
            >
              Optional: Übergeordnete Fähigkeit
            </summary>
            <div className="px-3 pb-3 pt-1">
              <label
                htmlFor="reactive-parent-skill"
                className={`${T.tinyBold} block mb-1`}
              >
                parent_skill (Fähigkeits-ID oder -Name)
              </label>
              <input
                id="reactive-parent-skill"
                type="text"
                value={parentSkill}
                onChange={(e) => setParentSkill(e.target.value)}
                placeholder="z.B. compare-numbers"
                className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Leer lassen, wenn diese Fähigkeit eigenständig ist.
              </p>
            </div>
          </details>

          {/* Raw-data accordion */}
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

          {!canSubmit && (name.trim() || domainRules.trim()) && (
            <p className={`${T.tiny} text-amber-300`}>
              {!hasTrigger &&
                "Mindestens eine Trigger-Bedingung (Verdict / Regex / Topic) wählen. "}
              {!domainRules.trim() && "Domain-Regel ist Pflicht."}
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

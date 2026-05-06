import { useMemo, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDecide,
  type ActionProposalAlternative,
  type GuidanceConsulted,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

type Choice = "recommended" | "alt" | "override";

export function ActionProposalPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "pending_proposal") return <></>;
  const node = view.proposal;
  const payload = node.payload;
  const stepKind = String(payload.step_kind ?? "");
  const reasoning = payload.reasoning ? String(payload.reasoning) : "";
  const recommended = useMemo<ActionProposalAlternative | null>(() => {
    const r = payload.recommended;
    if (r && typeof r === "object" && "label" in r) {
      return r as ActionProposalAlternative;
    }
    return null;
  }, [payload.recommended]);
  const alternatives = useMemo<ActionProposalAlternative[]>(() => {
    return Array.isArray(payload.alternatives)
      ? (payload.alternatives as ActionProposalAlternative[])
      : [];
  }, [payload.alternatives]);
  const guidance = useMemo<GuidanceConsulted[]>(() => {
    return Array.isArray(payload.guidance_consulted)
      ? (payload.guidance_consulted as GuidanceConsulted[])
      : [];
  }, [payload.guidance_consulted]);

  const overrideAllowed = stepKind !== "search";

  const [choice, setChoice] = useState<Choice>("recommended");
  const [altIndex, setAltIndex] = useState<number>(0);
  const [overrideText, setOverrideText] = useState<string>("");
  const [reason, setReason] = useState<string>("");

  const decide = useDecide(token, sessionId);
  const { error: toastError } = useToast();

  const overrideEmpty = choice === "override" && !overrideText.trim();
  const altMissing =
    choice === "alt" && (alternatives.length === 0 || altIndex < 0);
  const disabled = decide.isPending || overrideEmpty || altMissing;

  async function handleDecide(): Promise<void> {
    try {
      const body: Parameters<typeof decide.mutateAsync>[0] = {
        proposal_node_id: node.node_id,
        accepted: choice,
      };
      if (choice === "alt") body.alt_index = altIndex;
      if (choice === "override") body.override = overrideText;
      if (reason.trim()) body.reason = reason.trim();
      await decide.mutateAsync(body);
      // The pending tile vanishes on refetch; clear selection.
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title={`Vorschlag · ${stepKind}`}
        onClose={() => onSelectView(null)}
      />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Schritt</p>
          <p className={`text-white ${T.mono}`}>{stepKind}</p>
        </div>
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {reasoning}
            </p>
          </div>
        )}
        {guidance.length > 0 && (
          <div>
            <p className={T.tinyBold}>Konsultierte Hinweise</p>
            <ul className="mt-1 space-y-1">
              {guidance.map((g, idx) => (
                <li
                  key={`${g.kind}-${g.id}-${idx}`}
                  className="flex items-start gap-2"
                >
                  <span
                    className={`shrink-0 px-1.5 py-0.5 rounded ${T.tiny} ${
                      g.kind === "approach"
                        ? "bg-emerald-900/60 text-emerald-200"
                        : "bg-amber-900/60 text-amber-200"
                    }`}
                  >
                    {g.kind}
                  </span>
                  <span className={`text-slate-200 ${T.tiny}`}>
                    <span className={`${T.mono} text-slate-400`}>{g.id}</span>{" "}
                    — {g.summary}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="space-y-2 pt-2 border-t border-navy-700">
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="choice"
              checked={choice === "recommended"}
              onChange={() => setChoice("recommended")}
              className="mt-0.5"
            />
            <div className="flex-1 min-w-0">
              <p className={`text-white ${T.body}`}>Empfehlung übernehmen</p>
              {recommended && (
                <p className={`text-slate-300 ${T.tiny}`}>
                  {recommended.label}
                </p>
              )}
            </div>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="choice"
              checked={choice === "alt"}
              onChange={() => setChoice("alt")}
              disabled={alternatives.length === 0}
              className="mt-0.5"
            />
            <div className="flex-1 min-w-0">
              <p
                className={`${T.body} ${
                  alternatives.length === 0 ? "text-slate-500" : "text-white"
                }`}
              >
                Alternative wählen
              </p>
              {choice === "alt" && alternatives.length > 0 && (
                <select
                  value={altIndex}
                  onChange={(e) => setAltIndex(Number(e.target.value))}
                  className={`mt-1 w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
                >
                  {alternatives.map((a, idx) => (
                    <option key={idx} value={idx}>
                      {a.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="choice"
              checked={choice === "override"}
              onChange={() => setChoice("override")}
              disabled={!overrideAllowed}
              className="mt-0.5"
            />
            <div className="flex-1 min-w-0">
              <p
                className={`${T.body} ${
                  overrideAllowed ? "text-white" : "text-slate-500"
                }`}
              >
                Eigene Eingabe
              </p>
              {!overrideAllowed && (
                <p className={`text-slate-500 ${T.tiny}`}>
                  Nicht erlaubt für Schritt &quot;search&quot;.
                </p>
              )}
              {choice === "override" && overrideAllowed && (
                <textarea
                  value={overrideText}
                  onChange={(e) => setOverrideText(e.target.value)}
                  rows={4}
                  placeholder={overridePlaceholder(stepKind)}
                  className={`mt-1 w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
                />
              )}
            </div>
          </label>
        </div>

        <div>
          <label htmlFor="reason" className={`${T.tinyBold} block mb-1`}>
            Begründung (optional)
          </label>
          <textarea
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
          />
          <p className={`text-slate-500 ${T.tiny} mt-1`}>
            Begründung hilft dem System, beim nächsten Mal besser zu empfehlen.
          </p>
        </div>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleDecide()}
          disabled={disabled}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {decide.isPending ? "Entscheide…" : "Entscheiden"}
        </button>
        {decide.error && (
          <p className={`text-red-400 ${T.tiny}`}>{decide.error.message}</p>
        )}
      </footer>
    </div>
  );
}

function overridePlaceholder(stepKind: string): string {
  switch (stepKind) {
    case "extract_claims":
      return "Freitext — wird in Sätze zerlegt zu Aussagen.";
    case "formulate_task":
      return "Suchanfrage als Text.";
    case "evaluate":
      return "Freitext-Begründung (Verdict wird zu manual).";
    case "propose_stop":
      return "Begründung für den Stopp.";
    default:
      return "";
  }
}

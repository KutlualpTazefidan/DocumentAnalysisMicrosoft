import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { ExpertCorrectionPanel } from "../../../src/admin/provenienz/panels/ExpertCorrectionPanel";
import { ToastProvider } from "../../../src/shared/components/Toaster";
import type {
  ExpertMethodRequestView,
  ExpertStepOverrideView,
} from "../../../src/admin/provenienz/layout";
import type { ProvNode } from "../../../src/admin/hooks/useProvenienz";

/**
 * Phase-3 ExpertCorrectionPanel covers BOTH new override kinds via
 * one panel (the view shape — correction Node + target_proposal_node_id
 * — is identical; only the wording + accent differ). These tests
 * exercise the kind-aware branches so the rose-vs-amber framing and
 * the wishlist-vs-corpus footer hint render correctly.
 */

function correctionNode(
  kind: "expert_step_override" | "expert_method_request",
  payload: Record<string, unknown>,
): ProvNode {
  return {
    node_id: "01EC",
    session_id: "01SID",
    kind,
    payload,
    actor: "human",
    created_at: "2026-06-01T10:00:00Z",
  };
}

function Wrapper({ children }: { children: ReactNode }): JSX.Element {
  return <ToastProvider>{children}</ToastProvider>;
}

function renderWith(
  view: ExpertStepOverrideView | ExpertMethodRequestView,
): void {
  render(
    <Wrapper>
      <ExpertCorrectionPanel
        sessionId="01SID"
        token="tok"
        view={view}
        nodes={[view.correction]}
        edges={[]}
        onSelectView={vi.fn()}
      />
    </Wrapper>,
  );
}

describe("ExpertCorrectionPanel — expert_step_override", () => {
  it("renders the rose 'Korrektur' framing with the corpus-feedback footer hint", () => {
    const node = correctionNode("expert_step_override", {
      intended_step: "formulate_task",
      reason: "Task formulieren passt hier besser.",
      target_step_kind: "extract_claims",
      target_proposal_node_id: "01PLAN",
    });
    renderWith({
      view_id: "view:01EC",
      kind: "expert_step_override",
      correction: node,
      target_proposal_node_id: "01PLAN",
    });
    // Header reads "Korrektur" (Purpose 1 — teach the agent).
    expect(screen.getByText("Korrektur")).toBeInTheDocument();
    expect(screen.getByText("statt extract_claims")).toBeInTheDocument();
    expect(screen.getByText("Vorgeschlagener Schritt")).toBeInTheDocument();
    expect(screen.getByText("formulate_task")).toBeInTheDocument();
    expect(
      screen.getByText("Task formulieren passt hier besser."),
    ).toBeInTheDocument();
    // Footer hint mentions NOTE-skill corpus, NOT the wishlist.
    expect(screen.getByText(/NOTE-Skill im Korpus/i)).toBeInTheDocument();
    expect(screen.queryByText(/Capability-Wunschliste/i)).not.toBeInTheDocument();
  });
});

describe("ExpertCorrectionPanel — expert_method_request", () => {
  it("renders the amber 'Methoden-Wunsch' framing with the wishlist footer hint", () => {
    const node = correctionNode("expert_method_request", {
      intended_step: "summarize_section",
      name: "summarize_section",
      description: "Chunk braucht erst eine Zusammenfassung.",
      reason: "Chunk braucht erst eine Zusammenfassung.",
      target_step_kind: "extract_claims",
      target_proposal_node_id: "01PLAN",
    });
    renderWith({
      view_id: "view:01EC",
      kind: "expert_method_request",
      correction: node,
      target_proposal_node_id: "01PLAN",
    });
    // Header reads "Methoden-Wunsch" (Purpose 2 — capability gap).
    expect(screen.getByText("Methoden-Wunsch")).toBeInTheDocument();
    expect(screen.getByText("Gewünschte Methode")).toBeInTheDocument();
    expect(screen.getByText("summarize_section")).toBeInTheDocument();
    // The Capability-Wunschliste phrase appears twice — once in the
    // inline hint right under the method name, once in the footer
    // explaining where the wish flows. Both are intentional.
    expect(
      screen.getAllByText(/Capability-Wunschliste/i).length,
    ).toBeGreaterThanOrEqual(2);
    // Footer hint does NOT mention the NOTE-skill corpus (that's the
    // step_override path's framing).
    expect(screen.queryByText(/NOTE-Skill im Korpus/i)).not.toBeInTheDocument();
  });
});

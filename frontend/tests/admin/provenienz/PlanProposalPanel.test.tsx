import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { PlanProposalPanel } from "../../../src/admin/provenienz/panels/PlanProposalPanel";
import { ToastProvider } from "../../../src/shared/components/Toaster";
import type { PlanProposalView } from "../../../src/admin/provenienz/layout";
import type { ProvNode } from "../../../src/admin/hooks/useProvenienz";

// ── fixtures ─────────────────────────────────────────────────────────────

const planNode: ProvNode = {
  node_id: "01PLAN",
  session_id: "01SID",
  kind: "plan_proposal",
  actor: "planner",
  created_at: "2026-05-31T20:00:00Z",
  payload: {
    kind: "executable_step",
    name: "extract_claims",
    description: "Extract atomic claims from the chunk",
    reasoning: "Chunk has multiple distinct factual claims to extract.",
    considered_alternatives: [
      {
        name: "formulate_task",
        kind: "executable_step",
        why_not: "No focus claim yet",
      },
    ],
    confidence: 0.9,
    tool: null,
    approach_id: null,
    anchor_node_id: "01CHUNK",
    triggered_from_node_id: "",
  },
};

const planView: PlanProposalView = {
  view_id: "view:01PLAN",
  kind: "plan_proposal",
  plan: planNode,
  consumed: false,
};

const agentInfoFixture = {
  llm: { backend: "vllm", model: "qwen3-8b" },
  next_step: { name: "next_step", system_prompt: "", rules: [] },
  valid_steps_per_anchor: {
    chunk: ["extract_claims", "propose_stop"],
    claim: ["formulate_task", "propose_stop"],
    task: ["search", "propose_stop"],
  },
  steps: [],
  tools: [],
  rules: {},
};

// ── MSW server ───────────────────────────────────────────────────────────
// Each test mints fresh handlers via server.use(); the always-on /agent-info
// handler keeps the combobox source available without per-test boilerplate.

const server = setupServer(
  http.get("*/api/admin/provenienz/agent-info", () => HttpResponse.json(agentInfoFixture)),
);

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers(
    http.get("*/api/admin/provenienz/agent-info", () => HttpResponse.json(agentInfoFixture)),
  );
});
afterAll(() => server.close());

beforeEach(() => {
  sessionStorage.setItem("goldens.api_token", "tok");
});

// ── render harness ────────────────────────────────────────────────────────

function makeWrapper(): (props: { children: ReactNode }) => JSX.Element {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}

function renderPanel(): { onSelectView: ReturnType<typeof vi.fn> } {
  const Wrapper = makeWrapper();
  const onSelectView = vi.fn();
  render(
    <Wrapper>
      <PlanProposalPanel
        sessionId="01SID"
        token="tok"
        view={planView}
        nodes={[planNode]}
        edges={[]}
        onSelectView={onSelectView}
      />
    </Wrapper>,
  );
  return { onSelectView };
}

// ── tests ────────────────────────────────────────────────────────────────

describe("PlanProposalPanel — idle state", () => {
  it("renders Akzeptieren and Verwerfen buttons with the Begründung section", async () => {
    renderPanel();
    expect(
      await screen.findByRole("button", { name: /Akzeptieren/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Verwerfen/i })).toBeInTheDocument();
    // Begründung section header from the panel body
    expect(screen.getByText(/Begründung/i)).toBeInTheDocument();
    expect(screen.getByText(/multiple distinct factual claims/i)).toBeInTheDocument();
    // Inline form elements absent in idle state
    expect(screen.queryByLabelText(/Stattdessen…/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Warum\?/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Korrektur erfassen/i }),
    ).not.toBeInTheDocument();
  });
});

describe("PlanProposalPanel — Verwerfen morph", () => {
  it("first Verwerfen click morphs button into inline form", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));

    // Form fields appear
    expect(screen.getByLabelText(/Stattdessen…/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Warum\?/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Korrektur erfassen/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Doch löschen/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Abbrechen/i })).toBeInTheDocument();
    // Original Verwerfen button is replaced by the form (so users can't
    // accidentally double-fire delete + override).
    expect(screen.queryByRole("button", { name: /^Verwerfen$/i })).not.toBeInTheDocument();
    // Akzeptieren disabled while the form is open to avoid race conditions.
    expect(screen.getByRole("button", { name: /Akzeptieren/i })).toBeDisabled();
  });

  it("combobox accepts free-text for unimplemented step names", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));

    const stepInput = screen.getByLabelText(/Stattdessen…/i) as HTMLInputElement;
    await user.type(stepInput, "summarize_section");
    expect(stepInput.value).toBe("summarize_section");
    // Amber hint surfaces once the typed step is not in the known set.
    expect(
      screen.getByText(/wird auch als Capability-Wunsch erfasst/i),
    ).toBeInTheDocument();
  });

  it("Submit fires POST /decide with the typed expert_correction body", async () => {
    const decideHandler = vi.fn((body: unknown) => body);
    server.use(
      http.post("*/api/admin/provenienz/sessions/:sid/decide", async ({ request }) => {
        const body = await request.json();
        decideHandler(body);
        return HttpResponse.json(
          {
            decision_node: { node_id: "01DEC", kind: "decision" },
            spawned_nodes: [],
            spawned_edges: [],
          },
          { status: 201 },
        );
      }),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen…/i), "formulate_task");
    await user.type(
      screen.getByLabelText(/Warum\?/i),
      "Task formulieren passt besser.",
    );
    await user.click(screen.getByRole("button", { name: /Korrektur erfassen/i }));

    await waitFor(() => expect(decideHandler).toHaveBeenCalledTimes(1));
    expect(decideHandler).toHaveBeenCalledWith({
      proposal_node_id: "01PLAN",
      expert_correction: {
        intended_step: "formulate_task",
        intended_args: {},
        reason: "Task formulieren passt besser.",
      },
    });
    // Panel closes (onSelectView(null)) after a successful submit.
    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
  });

  it("Submit disabled with empty reason; no POST fires", async () => {
    const decideHandler = vi.fn();
    server.use(
      http.post("*/api/admin/provenienz/sessions/:sid/decide", () => {
        decideHandler();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen…/i), "formulate_task");
    // Reason stays empty.

    const submit = screen.getByRole("button", { name: /Korrektur erfassen/i });
    expect(submit).toBeDisabled();
    // Even when clicked, the disabled button does not fire.
    await user.click(submit);
    expect(decideHandler).not.toHaveBeenCalled();
  });

  it("Esc collapses form back to Verwerfen button without submitting", async () => {
    const decideHandler = vi.fn();
    server.use(
      http.post("*/api/admin/provenienz/sessions/:sid/decide", () => {
        decideHandler();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    expect(screen.getByLabelText(/Stattdessen…/i)).toBeInTheDocument();

    await user.keyboard("{Escape}");
    // Form gone, original buttons back.
    expect(screen.queryByLabelText(/Stattdessen…/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Verwerfen$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Akzeptieren/i })).toBeEnabled();
    expect(decideHandler).not.toHaveBeenCalled();
  });
});

describe("PlanProposalPanel — Akzeptieren regression", () => {
  it("Akzeptieren still routes to the step-specific endpoint, not /decide", async () => {
    // Capture both routes — only /extract-claims should fire.
    const decideHandler = vi.fn();
    const extractHandler = vi.fn();
    server.use(
      http.post("*/api/admin/provenienz/sessions/:sid/decide", () => {
        decideHandler();
        return HttpResponse.json({}, { status: 201 });
      }),
      http.post(
        "*/api/admin/provenienz/sessions/:sid/extract-claims",
        async ({ request }) => {
          const body = (await request.json()) as { chunk_node_id: string };
          extractHandler(body);
          return HttpResponse.json({
            node_id: "01ACT",
            kind: "action_proposal",
            payload: {},
          });
        },
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Akzeptieren/i }));

    await waitFor(() => expect(extractHandler).toHaveBeenCalledTimes(1));
    expect(extractHandler).toHaveBeenCalledWith({
      chunk_node_id: "01CHUNK",
      triggered_from_node_id: undefined,
    });
    expect(decideHandler).not.toHaveBeenCalled();
    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
  });
});

describe("PlanProposalPanel — keyboard tab order", () => {
  it("opens form via Verwerfen and tab order lands on combobox → textarea → submit", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));

    const stepInput = screen.getByLabelText(/Stattdessen…/i);
    // autoFocus on the combobox input means the form opens with focus already
    // on it — no Tab needed to get there.
    expect(stepInput).toHaveFocus();
    // Type a step + reason so the submit button enables; otherwise it's
    // skipped from the tab sequence as a disabled control.
    await user.keyboard("formulate_task");

    await user.tab();
    const reasonInput = screen.getByLabelText(/Warum\?/i);
    expect(reasonInput).toHaveFocus();
    await user.keyboard("erstmal Begründung");

    await user.tab();
    expect(screen.getByRole("button", { name: /Korrektur erfassen/i })).toHaveFocus();
  });
});

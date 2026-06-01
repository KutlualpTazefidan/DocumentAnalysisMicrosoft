import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

function renderPanel(
  opts: { view?: PlanProposalView } = {},
): { onSelectView: ReturnType<typeof vi.fn> } {
  const Wrapper = makeWrapper();
  const onSelectView = vi.fn();
  render(
    <Wrapper>
      <PlanProposalPanel
        sessionId="01SID"
        token="tok"
        view={opts.view ?? planView}
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
      screen.queryByRole("button", { name: /^Korrektur erfassen$/i }),
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
      screen.getByRole("button", { name: /^Korrektur erfassen$/i }),
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
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    await waitFor(() => expect(decideHandler).toHaveBeenCalledTimes(1));
    expect(decideHandler).toHaveBeenCalledWith({
      proposal_node_id: "01PLAN",
      expert_correction: {
        intended_step: "formulate_task",
        intended_args: {},
        reason: "Task formulieren passt besser.",
        post_hoc: false,
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

    const submit = screen.getByRole("button", { name: /^Korrektur erfassen$/i });
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
    expect(screen.getByRole("button", { name: /^Korrektur erfassen$/i })).toHaveFocus();
  });
});

// ── Phase-2: post-hoc correction drawer ────────────────────────────────

describe("PlanProposalPanel — post-hoc drawer", () => {
  it("renders the drawer toggle in idle state alongside Akzeptieren/Verwerfen", async () => {
    renderPanel();
    expect(
      await screen.findByRole("button", { name: /Akzeptieren/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Verwerfen$/i })).toBeInTheDocument();
    expect(
      screen.getByTestId("plan-posthoc-toggle"),
    ).toHaveTextContent(/Im Nachhinein/i);
  });

  it("hides Akzeptieren+Verwerfen but keeps the drawer when the plan is consumed", () => {
    // Once a downstream action_proposal exists, firing Akzeptieren again
    // would double-execute the step, so the decision-time footer is
    // removed. The drawer remains so the user can still capture an
    // after-the-fact "I realised too late" correction.
    const consumedView: PlanProposalView = { ...planView, consumed: true };
    renderPanel({ view: consumedView });
    expect(
      screen.queryByRole("button", { name: /Akzeptieren/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Verwerfen$/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("plan-posthoc-toggle")).toBeInTheDocument();
  });

  it("clicking the drawer toggle expands the same correction form (combobox + textarea)", async () => {
    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("plan-posthoc-toggle"));

    // Form fields appear inside the drawer.
    expect(screen.getByLabelText(/Stattdessen…/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Warum\?/i)).toBeInTheDocument();
    // Slate-accented submit button reads as a sibling of the Verwerfen
    // flow but distinguishes itself with the "(im Nachhinein)" tag.
    expect(
      screen.getByRole("button", { name: /Korrektur \(im Nachhinein\) erfassen/i }),
    ).toBeInTheDocument();
    // The drawer must NOT carry a "Doch löschen" button — deletion is
    // tied to the decision-time footer (Verwerfen), not the after-the-
    // fact reflective path.
    expect(
      screen.queryByRole("button", { name: /Doch löschen/i }),
    ).not.toBeInTheDocument();
  });

  it("submitting the post-hoc form POSTs /decide with post_hoc=true", async () => {
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
    await user.click(screen.getByTestId("plan-posthoc-toggle"));
    await user.type(screen.getByLabelText(/Stattdessen…/i), "formulate_task");
    await user.type(
      screen.getByLabelText(/Warum\?/i),
      "im Nachhinein gemerkt: Task wäre besser gewesen.",
    );
    await user.click(
      screen.getByRole("button", { name: /Korrektur \(im Nachhinein\) erfassen/i }),
    );

    await waitFor(() => expect(decideHandler).toHaveBeenCalledTimes(1));
    expect(decideHandler).toHaveBeenCalledWith({
      proposal_node_id: "01PLAN",
      expert_correction: {
        intended_step: "formulate_task",
        intended_args: {},
        reason: "im Nachhinein gemerkt: Task wäre besser gewesen.",
        post_hoc: true,
      },
    });
    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
  });

  it("Esc collapses the drawer back to the toggle without submitting", async () => {
    const decideHandler = vi.fn();
    server.use(
      http.post("*/api/admin/provenienz/sessions/:sid/decide", () => {
        decideHandler();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("plan-posthoc-toggle"));
    expect(screen.getByLabelText(/Stattdessen…/i)).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByLabelText(/Stattdessen…/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("plan-posthoc-toggle")).toBeInTheDocument();
    expect(decideHandler).not.toHaveBeenCalled();
  });
});

// ── Phase-RGA: clarifying-state ──────────────────────────────────────────

describe("PlanProposalPanel — Reasoning-Gap-Analysis clarifying state", () => {
  it("transitions to clarifying when /decide response carries clarification", async () => {
    // MSW handler: /decide returns clarification block on submit
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () => {
          return HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: {
                question: "Bitte erläutern Sie, was am Knoten »formulate_task« nahelegt — was haben Sie gesehen?",
                score: 1,
                override_node_id: "01OVR",
              },
            },
            { status: 201 },
          );
        },
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen/i), "formulate_task");
    await user.type(
      screen.getByLabelText(/Warum\?/i),
      "Konstrukt-Definition.",
    );
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    // Panel does NOT close — instead, the clarifying section appears.
    await waitFor(() =>
      expect(screen.getByTestId("plan-clarifying-section")).toBeInTheDocument(),
    );
    expect(onSelectView).not.toHaveBeenCalled();

    // Agent's question rendered in role=status, aria-live=polite
    const questionRegion = screen.getByRole("status");
    expect(questionRegion).toHaveAttribute("aria-live", "polite");
    expect(questionRegion).toHaveTextContent(/Bitte erläutern Sie/);

    // Readonly summary of the override above. Scope to the clarifying
    // section AND exclude role=status (the agent's question echoes the
    // step name back at the expert) so getByText (singular) hits only
    // the readonly summary span, not the question text — and not the
    // considered_alternatives list outside the clarifying section.
    const section = screen.getByTestId("plan-clarifying-section");
    const stattdessenLabel = within(section).getByText(/^Stattdessen:$/);
    expect(stattdessenLabel.parentElement).toHaveTextContent(/formulate_task/);
    const begruendungLabel = within(section).getByText(/^Begründung:$/);
    expect(begruendungLabel.parentElement).toHaveTextContent(
      /Konstrukt-Definition/,
    );

    // Buttons rendered
    expect(
      screen.getByRole("button", { name: /Klarstellung absenden/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Ohne Antwort schließen/i }),
    ).toBeInTheDocument();
  });

  it("submits clarification via POST /clarify and closes panel", async () => {
    let clarifyBody: unknown = null;
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () =>
          HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: {
                question: "Erklären Sie bitte.",
                score: 1,
                override_node_id: "01OVR",
              },
            },
            { status: 201 },
          ),
      ),
      http.post(
        "*/api/admin/provenienz/sessions/:sid/clarify",
        async ({ request }) => {
          clarifyBody = await request.json();
          return HttpResponse.json(
            {
              override_node: { node_id: "01OVR", kind: "expert_step_override" },
              spawned_nodes: [],
              spawned_edges: [],
            },
            { status: 201 },
          );
        },
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    // Walk through Verwerfen → form → submit (triggers clarifying)
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen/i), "formulate_task");
    await user.type(screen.getByLabelText(/Warum\?/i), "weil.");
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    // Wait for clarifying state
    await waitFor(() =>
      expect(screen.getByTestId("plan-clarifying-section")).toBeInTheDocument(),
    );

    // Type the clarification + submit
    await user.type(
      screen.getByLabelText(/Ihre Klarstellung/i),
      "Der Term verweist auf eine Variable.",
    );
    await user.click(
      screen.getByRole("button", { name: /Klarstellung absenden/i }),
    );

    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
    expect(clarifyBody).toEqual({
      override_node_id: "01OVR",
      clarification: "Der Term verweist auf eine Variable.",
      skipped: false,
    });
  });

  it("skip-button posts /clarify with skipped=true and closes panel", async () => {
    let clarifyBody: unknown = null;
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () =>
          HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: {
                question: "Erklären?",
                score: 1,
                override_node_id: "01OVR",
              },
            },
            { status: 201 },
          ),
      ),
      http.post(
        "*/api/admin/provenienz/sessions/:sid/clarify",
        async ({ request }) => {
          clarifyBody = await request.json();
          return HttpResponse.json(
            {
              override_node: { node_id: "01OVR", kind: "expert_step_override" },
              spawned_nodes: [{ node_id: "01SKIP", kind: "clarification_skipped" }],
              spawned_edges: [{ edge_id: "01ED", kind: "annotates" }],
            },
            { status: 201 },
          );
        },
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen/i), "formulate_task");
    await user.type(screen.getByLabelText(/Warum\?/i), "x");
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    await waitFor(() =>
      expect(screen.getByTestId("plan-clarifying-section")).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /Ohne Antwort schließen/i }),
    );

    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
    expect(clarifyBody).toEqual({
      override_node_id: "01OVR",
      clarification: "",
      skipped: true,
    });
  });

  it("Esc in clarifying state triggers the same skip flow", async () => {
    let clarifyBody: unknown = null;
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () =>
          HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: {
                question: "Warum?",
                score: 1,
                override_node_id: "01OVR",
              },
            },
            { status: 201 },
          ),
      ),
      http.post(
        "*/api/admin/provenienz/sessions/:sid/clarify",
        async ({ request }) => {
          clarifyBody = await request.json();
          return HttpResponse.json(
            {
              override_node: { node_id: "01OVR" },
              spawned_nodes: [],
              spawned_edges: [],
            },
            { status: 201 },
          );
        },
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen/i), "formulate_task");
    await user.type(screen.getByLabelText(/Warum\?/i), "x");
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    await waitFor(() =>
      expect(screen.getByTestId("plan-clarifying-section")).toBeInTheDocument(),
    );

    // Esc should fire the skip handler — funnels through handleClarifyExit
    await user.keyboard("{Escape}");

    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
    expect(clarifyBody).toMatchObject({
      override_node_id: "01OVR",
      skipped: true,
    });
  });

  it("obvious-path response (clarification=null) closes panel without entering clarifying", async () => {
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () =>
          HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: null,
            },
            { status: 201 },
          ),
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Verwerfen/i }));
    await user.type(screen.getByLabelText(/Stattdessen/i), "formulate_task");
    await user.type(screen.getByLabelText(/Warum\?/i), "x");
    await user.click(screen.getByRole("button", { name: /^Korrektur erfassen$/i }));

    // Panel closes as in pre-RGA behavior
    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
    expect(screen.queryByTestId("plan-clarifying-section")).not.toBeInTheDocument();
  });

  it("post-hoc drawer never enters clarifying state even if backend returned a clarification block", async () => {
    // Backend SHOULD never return clarification on post_hoc path (Step 4
    // short-circuit), but test the defensive boundary: the frontend
    // handleSubmitPostHoc must not transition to clarifying even if it
    // somehow received a clarification.
    server.use(
      http.post(
        "*/api/admin/provenienz/sessions/:sid/decide",
        async () =>
          HttpResponse.json(
            {
              decision_node: { node_id: "01DEC", kind: "decision" },
              spawned_nodes: [{ node_id: "01OVR", kind: "expert_step_override" }],
              spawned_edges: [],
              clarification: {
                question: "Should not appear in UI",
                score: 1,
                override_node_id: "01OVR",
              },
            },
            { status: 201 },
          ),
      ),
    );

    const { onSelectView } = renderPanel();
    const user = userEvent.setup();
    // Open the post-hoc drawer (NOT the Verwerfen form)
    await user.click(screen.getByRole("button", { name: /Im Nachhinein/i }));
    // The post-hoc drawer's form looks similar to Verwerfen-form;
    // submit through it
    const inputs = screen.getAllByLabelText(/Stattdessen/i);
    const reasonInputs = screen.getAllByLabelText(/Warum\?/i);
    // Use the LAST input (post-hoc one is below the Verwerfen one in DOM)
    await user.type(inputs[inputs.length - 1], "summarize_section");
    await user.type(reasonInputs[reasonInputs.length - 1], "Im Nachhinein.");
    // Find the post-hoc submit button
    const postHocSubmit = screen.getByRole("button", {
      name: /Korrektur \(im Nachhinein\) erfassen/i,
    });
    await user.click(postHocSubmit);

    // Panel closes per post-hoc semantics — clarification block ignored
    await waitFor(() => expect(onSelectView).toHaveBeenCalledWith(null));
    expect(screen.queryByTestId("plan-clarifying-section")).not.toBeInTheDocument();
  });
});

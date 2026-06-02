import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Phase-4 Wishlist UI evolution — unit-level coverage for the
 * CapabilityRequestsTab component. The integration with the backend
 * aggregator (count_by_actor bucketing, ordering) is already pinned by
 * the Step-6 backend tests; here we just verify that the component
 * renders the aggregator output correctly:
 *
 *   - F1: header pill renders {count}× · {H}E / {A}A
 *   - F2/F3: violet Experte / sky Agent badge per example.actor
 *   - F4/F5: empty/unknown actor defaults to Agent
 *   - F6: hook order preserved (no client-side re-sort)
 *   - F7/F8: subtitle + empty-state copy frames both sources
 *
 * useCapabilityRequests is mocked directly via vi.mock — no
 * QueryClient/MSW overhead needed.
 */

vi.mock("../../../src/admin/hooks/useProvenienz", async () => {
  const actual = await vi.importActual<
    typeof import("../../../src/admin/hooks/useProvenienz")
  >("../../../src/admin/hooks/useProvenienz");
  return {
    ...actual,
    useCapabilityRequests: vi.fn(),
  };
});

import { CapabilityRequestsTab } from "../../../src/admin/provenienz/CapabilityRequestsTab";
import {
  useCapabilityRequests,
  type CapabilityRequestAggregation,
  type CapabilityRequestExample,
} from "../../../src/admin/hooks/useProvenienz";

// ── fixture helpers ──────────────────────────────────────────────────────

function makeExample(
  overrides: Partial<CapabilityRequestExample> = {},
): CapabilityRequestExample {
  return {
    session_id: "01SESSION0123456789",
    slug: "doc-slug",
    node_id: "01EXAMPLE",
    description: "",
    reasoning: "",
    created_at: "2026-06-01T10:00:00Z",
    actor: "agent",
    ...overrides,
  };
}

function mockData(data: CapabilityRequestAggregation[]): void {
  vi.mocked(useCapabilityRequests).mockReturnValue({
    data,
    isLoading: false,
    error: null,
  } as never);
}

function renderTab(): void {
  render(<CapabilityRequestsTab token="tok" />);
}

// ── tests ────────────────────────────────────────────────────────────────

describe("CapabilityRequestsTab — header pill (F1)", () => {
  it("renders header pill {count}× · {humanCount}E / {agentCount}A for a method", () => {
    mockData([
      {
        name: "summarize_section",
        count: 3,
        count_by_actor: { human: 2, agent: 1 },
        examples: [],
      },
    ]);
    renderTab();
    // The pill text contains U+00D7 (×) and U+00B7 (·) from the
    // component source — same code-points used here.
    expect(screen.getByText("3× · 2E / 1A")).toBeInTheDocument();
  });
});

describe("CapabilityRequestsTab — example actor badges (F2/F3)", () => {
  it("renders violet 'Experte' badge for an example with actor='human'", () => {
    mockData([
      {
        name: "summarize_section",
        count: 1,
        count_by_actor: { human: 1, agent: 0 },
        examples: [makeExample({ node_id: "01EX1", actor: "human" })],
      },
    ]);
    renderTab();
    // RTL queries the DOM not the rendered viewport — children of a
    // collapsed <details> are findable without expanding it.
    const badge = screen.getByText("Experte");
    expect(badge).toBeInTheDocument();
    // Substring match on the colour name — the exact Tailwind classes
    // (bg-violet-900/40 text-violet-200 border-violet-700/50) are
    // brittle, but the "violet" stem is the stable signal.
    expect(badge.className).toMatch(/violet/);
    // aria-label is the screen-reader hook tying the badge to the
    // "Experten-Vorgabe" source framing.
    expect(
      screen.getByLabelText("Quelle: Experten-Vorgabe"),
    ).toBeInTheDocument();
  });

  it("renders sky 'Agent' badge for an example with actor='agent'", () => {
    mockData([
      {
        name: "summarize_section",
        count: 1,
        count_by_actor: { human: 0, agent: 1 },
        examples: [makeExample({ node_id: "01EX1", actor: "agent" })],
      },
    ]);
    renderTab();
    const badge = screen.getByText("Agent");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toMatch(/sky/);
    expect(
      screen.getByLabelText("Quelle: Agent-Anfrage"),
    ).toBeInTheDocument();
  });
});

describe("CapabilityRequestsTab — actor defaults (F4/F5)", () => {
  it("defaults to Agent badge when example actor is empty string", () => {
    mockData([
      {
        name: "summarize_section",
        count: 1,
        count_by_actor: { human: 0, agent: 1 },
        examples: [makeExample({ node_id: "01EX1", actor: "" })],
      },
    ]);
    renderTab();
    // Component branches on `ex.actor === "human"`; empty string falls
    // through to the Agent branch.
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.queryByText("Experte")).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Quelle: Agent-Anfrage"),
    ).toBeInTheDocument();
  });

  it("defaults to Agent badge when example actor is unknown value", () => {
    mockData([
      {
        name: "summarize_section",
        count: 1,
        count_by_actor: { human: 0, agent: 1 },
        examples: [makeExample({ node_id: "01EX1", actor: "bot" })],
      },
    ]);
    renderTab();
    // Mirrors the backend default-to-agent bucketing pinned by Step-6
    // test test_..._count_by_actor_defaults_unknown_actor_to_agent.
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.queryByText("Experte")).not.toBeInTheDocument();
  });
});

describe("CapabilityRequestsTab — hook order (F6)", () => {
  it("renders methods in the order returned by the hook (no client-side re-sort)", () => {
    mockData([
      {
        name: "zebra_method",
        count: 5,
        count_by_actor: { human: 0, agent: 5 },
        examples: [],
      },
      {
        name: "alpha_method",
        count: 3,
        count_by_actor: { human: 3, agent: 0 },
        examples: [],
      },
    ]);
    renderTab();
    // The API's canonical sort (frequency desc, name asc) is the single
    // source of truth — the UI must NOT re-sort by name. We assert
    // document order matches hook order: zebra (high count) first,
    // alpha (low count) second.
    const items = screen.getAllByText(/_method$/);
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("zebra_method");
    expect(items[1]).toHaveTextContent("alpha_method");
  });
});

describe("CapabilityRequestsTab — subtitle copy (F7)", () => {
  it("subtitle copy frames both Agent and Experten sources", () => {
    mockData([]);
    renderTab();
    // The Phase-4 subtitle joins both sources with an em-dash in the
    // same paragraph — verify both phrases are in the document.
    expect(screen.getByText(/vom Agent angefragt/)).toBeInTheDocument();
    expect(screen.getByText(/vom Experten vorgegeben/)).toBeInTheDocument();
  });
});

describe("CapabilityRequestsTab — empty-state copy (F8)", () => {
  it("empty-state copy mentions both Agent and Experte sources", () => {
    mockData([]);
    renderTab();
    expect(
      screen.getByText(/Agent eine fehlende Fähigkeit meldet/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Experte eine Capability vorgibt/),
    ).toBeInTheDocument();
  });
});

describe("Phase-5 fade-treatment", () => {
  it("applies fade classes when count_by_actor.human === 0", () => {
    const fixture = [
      {
        name: "agent_only_method",
        count: 3,
        count_by_actor: { human: 0, agent: 3 },
        examples: [],
      },
    ];
    vi.mocked(useCapabilityRequests).mockReturnValue({
      data: fixture,
      isLoading: false,
      error: null,
    } as never);
    renderTab();
    const row = screen.getByText("agent_only_method").closest("li");
    expect(row).not.toBeNull();
    expect(row?.className).toMatch(/opacity-50/);
    expect(row?.className).toMatch(/hover:opacity-100/);
    expect(row?.className).toMatch(/focus-within:opacity-100/);
    expect(row?.className).toMatch(/transition-opacity/);
  });

  it("does NOT apply fade classes when count_by_actor.human >= 1", () => {
    const fixture = [
      {
        name: "expert_demanded",
        count: 3,
        count_by_actor: { human: 3, agent: 0 },
        examples: [],
      },
      {
        name: "mixed",
        count: 5,
        count_by_actor: { human: 1, agent: 4 },
        examples: [],
      },
    ];
    vi.mocked(useCapabilityRequests).mockReturnValue({
      data: fixture,
      isLoading: false,
      error: null,
    } as never);
    renderTab();
    const expertRow = screen.getByText("expert_demanded").closest("li");
    const mixedRow = screen.getByText("mixed").closest("li");
    expect(expertRow?.className).not.toMatch(/opacity-50/);
    expect(mixedRow?.className).not.toMatch(/opacity-50/);
  });

  it("sets aria-describedby on faded rows pointing to a hidden span with the explanation text", () => {
    const fixture = [
      {
        name: "agent_only_method",
        count: 3,
        count_by_actor: { human: 0, agent: 3 },
        examples: [],
      },
    ];
    vi.mocked(useCapabilityRequests).mockReturnValue({
      data: fixture,
      isLoading: false,
      error: null,
    } as never);
    renderTab();
    const row = screen.getByText("agent_only_method").closest("li");
    expect(row).not.toBeNull();
    const describedByValue = row?.getAttribute("aria-describedby");
    expect(describedByValue).toBeTruthy();
    // The test reads aria-describedby VALUE and finds the hidden span
    // via that ID, NOT a hardcoded string lookup. This way if the span
    // is moved or its className changes, the test still works.
    const hiddenSpan = describedByValue
      ? document.getElementById(describedByValue)
      : null;
    expect(hiddenSpan).not.toBeNull();
    expect(hiddenSpan?.textContent).toBe(
      "Nur von Agenten angefragt, keine Experten-Vorgabe.",
    );
  });
});

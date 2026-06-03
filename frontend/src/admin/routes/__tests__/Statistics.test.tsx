import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { Statistics } from "../Statistics";

vi.mock("../../../auth/useAuth", () => ({ useAuth: () => ({ token: "tok" }) }));

const server = setupServer(
  http.get("*/api/admin/statistics/extract/:slug", () =>
    HttpResponse.json({
      slug: "doc-a",
      diagnostics: { split: 0, no_decomposition: 0, clean: 0, total: 0 },
      register_boxes: 2,
      total_boxes: 5,
      register_rate: 0.4,
    })
  ),
  http.get("*/api/admin/statistics/synthese/:slug", () =>
    HttpResponse.json({
      slug: "doc-a",
      questions_created: 1,
      questions_deprecated: 0,
      survival_rate: 1,
      vote_approved: 0,
      vote_rejected: 0,
      vote_approval_rate: null,
      vote_distribution: [],
    })
  ),
  http.get("*/api/admin/statistics/provenienz/:slug", () =>
    HttpResponse.json({ slug: "doc-a", plan_proposals: 0, expert_overrides: 0, correction_rate: null })
  ),
  http.get("*/api/admin/statistics/capability-wishes", () => HttpResponse.json({ wishes: [] })),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("Statistics page", () => {
  it("renders three section headings", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/admin/doc/doc-a/statistics"]}>
          <Routes>
            <Route path="/admin/doc/:slug/statistics" element={<Statistics />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(screen.getByText("Extrahieren")).toBeInTheDocument();
      expect(screen.getByText("Synthese")).toBeInTheDocument();
      expect(screen.getByText("Provenienz")).toBeInTheDocument();
    });
  });
});

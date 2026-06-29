import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ToastProvider } from "../shared/components/Toaster";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ token: "tok", role: "admin", name: "x", tenantSlug: null, logout: () => {} }) }));

const server = setupServer(
  http.get("*/api/admin/docs", () => HttpResponse.json([])),
  http.get("*/api/admin/tenants", () => HttpResponse.json({ tenants: [] })),
  http.get("*/api/admin/statistics/extract/:slug", () => HttpResponse.json({ slug: "doc-a", diagnostics: { split: 0, no_decomposition: 0, clean: 0, total: 0 }, register_boxes: 0, total_boxes: 0, register_rate: 0 })),
  http.get("*/api/admin/statistics/synthese/:slug", () => HttpResponse.json({ slug: "doc-a", questions_created: 0, questions_deprecated: 0, survival_rate: 1, vote_approved: 0, vote_rejected: 0, vote_approval_rate: null, vote_distribution: [] })),
  http.get("*/api/admin/statistics/provenienz/:slug", () => HttpResponse.json({ slug: "doc-a", plan_proposals: 0, expert_overrides: 0, correction_rate: null })),
  http.get("*/api/admin/statistics/capability-wishes", () => HttpResponse.json({ wishes: [] })),
);
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("workspace routing", () => {
  it("legacy /admin/inbox redirects to /admin/files (Dateien tab)", async () => {
    renderAt("/admin/inbox");
    await waitFor(() => expect(screen.getByText("Dateien")).toBeInTheDocument());
  });

  it("legacy /admin/doc/:slug/statistics redirects to /admin/statistics?file=slug and renders", async () => {
    renderAt("/admin/doc/doc-a/statistics");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Extrahieren", level: 2 })).toBeInTheDocument());
  });

  it("statistics tab with no file shows the empty state", async () => {
    renderAt("/admin/statistics");
    await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
  });

  it("extract tab with no file shows the empty state", async () => {
    renderAt("/admin/extract");
    await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
  });

  it("synthese tab with no file shows the empty state", async () => {
    renderAt("/admin/synthesise");
    await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
  });
});

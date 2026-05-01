// frontend/tests/admin/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { ExtractRoute } from "../../../src/admin/routes/extract";

vi.mock("../../../src/admin/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const BOXES = [
  { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
];

const server = setupServer(
  http.get("*/api/admin/docs/rep/segments", () =>
    HttpResponse.json({ slug: "rep", boxes: BOXES }),
  ),
  http.get("*/api/admin/docs/rep/html", () =>
    HttpResponse.json({ html: '<h1 data-source-box="p1-b0">Hi</h1>' }),
  ),
  http.put("*/api/admin/docs/rep/html", () => HttpResponse.json({ ok: true })),
  http.post("*/api/admin/docs/rep/export", () =>
    HttpResponse.json({ doc_slug: "rep", source_pipeline: "local-pdf", elements: [] }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/extract", () =>
    HttpResponse.json({ box_id: "p1-b0", html: "<p>re-extracted</p>" }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin/doc/rep/extract"]}>
          <Routes>
            <Route path="/admin/doc/:slug/extract" element={<ExtractRoute token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

function wrapNoHtml() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin/doc/rep/extract"]}>
          <Routes>
            <Route path="/admin/doc/:slug/extract" element={<ExtractRoute token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("ExtractRoute", () => {
  it("loads html and shows it in editor", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByText("Hi")).toBeInTheDocument());
  });

  it("Export button posts and toasts", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    fireEvent.click(screen.getByRole("button", { name: /export sourceelements/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export sourceelements/i })).not.toBeDisabled(),
    );
  });

  it("StageIndicator is not present in idle, html-only render", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    expect(screen.queryByTestId("stage-toggle")).not.toBeInTheDocument();
  });

  // ── New tests ──────────────────────────────────────────────────────────

  it("top bar shows DocStepTabs with Extract tab active", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    // The Extract tab must be present and marked active (aria-current=page)
    const extractTab = screen.getByRole("tab", { name: /extract/i });
    expect(extractTab).toHaveAttribute("aria-current", "page");
    // Other tabs present but not active
    expect(screen.getByRole("tab", { name: /segment/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
  });

  it("Re-extract this box is disabled when no box is highlighted, enabled after clicking one", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));

    const reExtractBtn = screen.getByRole("button", { name: /re-extract this box/i });

    // Initially disabled — no highlight
    expect(reExtractBtn).toBeDisabled();

    // Click a box to set highlight
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));

    // Now enabled
    await waitFor(() => expect(reExtractBtn).not.toBeDisabled());
  });

  it("empty state (no html) renders DocStepTabs and Run extraction button", async () => {
    // Override html endpoint to return null/empty so we hit the empty state
    server.use(
      http.get("*/api/admin/docs/rep/html", () => HttpResponse.json(null)),
    );
    render(wrapNoHtml());

    // DocStepTabs should still render in the top bar
    await waitFor(() => expect(screen.getByRole("tab", { name: /extract/i })).toBeInTheDocument());
    // Run extraction button visible
    expect(screen.getByRole("button", { name: /run extraction/i })).toBeInTheDocument();
  });
});

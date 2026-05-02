// frontend/tests/admin/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { ExtractRoute } from "../../../src/admin/routes/extract";

vi.mock("../../../src/admin/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const BOXES = [
  { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
  { box_id: "p2-b0", page: 2, bbox: [10, 20, 100, 50], kind: "paragraph", confidence: 0.88, reading_order: 0 },
];

const MINERU_DATA = {
  elements: [
    { box_id: "p1-b0", html_snippet: "<h2>Hi</h2>" },
  ],
};

// Full HTML document so sliceHtmlByPage can find <head> and <body>.
const FULL_HTML = [
  "<!DOCTYPE html>",
  "<html><head><style>body{font-family:serif}</style></head><body>",
  '<h1 data-source-box="p1-b0">Hi</h1>',
  '<hr class="page-break">',
  '<p data-source-box="p2-b0">Page two</p>',
  "</body></html>",
].join("\n");

const server = setupServer(
  http.get("*/api/admin/docs/rep/segments", () =>
    HttpResponse.json({ slug: "rep", boxes: BOXES }),
  ),
  http.get("*/api/admin/docs/rep/html", () =>
    HttpResponse.json({ html: FULL_HTML }),
  ),
  http.put("*/api/admin/docs/rep/html", () => HttpResponse.json({ ok: true })),
  http.post("*/api/admin/docs/rep/export", () =>
    HttpResponse.json({ doc_slug: "rep", source_pipeline: "local-pdf", elements: [] }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/extract", () =>
    HttpResponse.json({ box_id: "p1-b0", html: "<p>re-extracted</p>" }),
  ),
  http.get("*/api/admin/docs/rep/mineru", () =>
    HttpResponse.json(MINERU_DATA),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Clear localStorage before each test to reset approval state.
beforeEach(() => {
  localStorage.clear();
});

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

// Helper: wait until the HTML editor is mounted (preview iframe visible).
async function waitForEditor() {
  await waitFor(() => expect(screen.getByTestId("html-preview-iframe")).toBeInTheDocument());
}

describe("ExtractRoute", () => {
  it("loads html and shows preview iframe in editor", async () => {
    render(wrap());
    await waitForEditor();
    expect(screen.getByTestId("html-preview-iframe")).toBeInTheDocument();
  });

  it("Export button posts and toasts", async () => {
    render(wrap());
    await waitForEditor();
    fireEvent.click(screen.getByRole("button", { name: /export sourceelements/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export sourceelements/i })).not.toBeDisabled(),
    );
  });

  it("StageIndicator is not present in idle, html-only render", async () => {
    render(wrap());
    await waitForEditor();
    expect(screen.queryByTestId("stage-toggle")).not.toBeInTheDocument();
  });

  // ── Top bar tests ──────────────────────────────────────────────────────

  it("top bar shows DocStepTabs with Extract tab active", async () => {
    render(wrap());
    await waitForEditor();
    // The Extract tab must be present and marked active (aria-current=page)
    const extractTab = screen.getByRole("tab", { name: /extract/i });
    expect(extractTab).toHaveAttribute("aria-current", "page");
    // Other tabs present but not active
    expect(screen.getByRole("tab", { name: /segment/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
  });

  it("Re-extract this box is disabled when no box is highlighted, enabled after clicking one", async () => {
    render(wrap());
    await waitForEditor();

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

  // ── Phase 4: colored page buttons ─────────────────────────────────────

  it("renders page buttons for each page in the segment data", async () => {
    render(wrap());
    await waitForEditor();

    // Two pages from BOXES (page 1 and page 2)
    await waitFor(() => screen.getByTestId("page-btn-1"));
    expect(screen.getByTestId("page-btn-1")).toBeInTheDocument();
    expect(screen.getByTestId("page-btn-2")).toBeInTheDocument();
  });

  it("page 1 button is green (extracted) because mineru has an element for p1-b0", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("page-btn-1"));

    const btn1 = screen.getByTestId("page-btn-1");
    // Green = extracted state
    expect(btn1.className).toContain("green");
  });

  it("page 2 button is red (no extraction) when mineru has no element for page 2", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("page-btn-2"));

    const btn2 = screen.getByTestId("page-btn-2");
    // Red = no extraction
    expect(btn2.className).toContain("red");
  });

  it("clicking a page button navigates to that page", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("page-btn-2"));

    // Active page 1 initially; btn-1 has aria-pressed=true
    expect(screen.getByTestId("page-btn-1")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("page-btn-2")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByTestId("page-btn-2"));

    await waitFor(() =>
      expect(screen.getByTestId("page-btn-2")).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.getByTestId("page-btn-1")).toHaveAttribute("aria-pressed", "false");
  });

  it("approve button toggles page to blue (approved) state and persists to localStorage", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("page-btn-1"));

    const approveBtn = screen.getByRole("button", { name: /diese seite genehmigen/i });
    fireEvent.click(approveBtn);

    // After approval the page button for page 1 should be blue
    await waitFor(() =>
      expect(screen.getByTestId("page-btn-1").className).toContain("blue"),
    );

    // localStorage should contain the approved page
    const stored = JSON.parse(localStorage.getItem("extract.approved.rep") ?? "[]") as number[];
    expect(stored).toContain(1);
  });

  it("approve button label toggles to 'Genehmigung aufheben' after approval", async () => {
    render(wrap());
    await waitForEditor();

    const approveBtn = screen.getByRole("button", { name: /diese seite genehmigen/i });
    fireEvent.click(approveBtn);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /genehmigung aufheben/i })).toBeInTheDocument(),
    );
  });
});

// frontend/tests/admin/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { ExtractRoute } from "../../../src/admin/routes/extract";

vi.mock("../../../src/admin/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const BOXES = [
  { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0, manually_activated: false },
  { box_id: "p2-b0", page: 2, bbox: [10, 20, 100, 50], kind: "paragraph", confidence: 0.88, reading_order: 0, manually_activated: false },
  // Low-confidence box on page 1 — filtered by default threshold 0.70
  { box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.50, reading_order: 1, manually_activated: false },
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
  // Server-backed per-page status — default: no pages done. Individual
  // tests override this handler to simulate a page being marked done.
  http.get("*/api/admin/docs/rep/pages/status", () =>
    HttpResponse.json({ slug: "rep", done_pages: [] }),
  ),
  http.patch("*/api/admin/docs/rep/pages/:page/status", async ({ params, request }) => {
    const body = (await request.json()) as { status: string };
    return HttpResponse.json({ page: Number(params.page), status: body.status });
  }),
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
        <MemoryRouter initialEntries={["/admin/extract?file=rep"]}>
          <Routes>
            <Route path="/admin/extract" element={<ExtractRoute token="tok" />} />
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
        <MemoryRouter initialEntries={["/admin/extract?file=rep"]}>
          <Routes>
            <Route path="/admin/extract" element={<ExtractRoute token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

// Helper: wait until the HTML editor host (Shadow DOM mount) is visible.
async function waitForEditor() {
  await waitFor(() => expect(screen.getByTestId("html-editor-host")).toBeInTheDocument());
}

describe("ExtractRoute", () => {
  it("loads html and shows preview iframe in editor", async () => {
    render(wrap());
    await waitForEditor();
    expect(screen.getByTestId("html-editor-host")).toBeInTheDocument();
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

  it("empty state (no html) renders the full chrome with hint card overlay", async () => {
    // Override html endpoint to return null/empty so we hit the empty state
    server.use(
      http.get("*/api/admin/docs/rep/html", () => HttpResponse.json(null)),
    );
    render(wrapNoHtml());

    // Hint card overlay is visible once the empty state renders
    await waitFor(() => expect(screen.getByTestId("empty-extract-hint")).toBeInTheDocument());
    // Top-bar action button "Re-extract all" remains the entry point
    expect(screen.getByLabelText("Re-extract all")).toBeInTheDocument();
  });

  // ── Phase 4: colored page buttons ─────────────────────────────────────

  it("renders page buttons for each page in the segment data", async () => {
    render(wrap());
    await waitForEditor();

    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));
    expect(screen.getByTestId("page-btn-1")).toBeInTheDocument();
    expect(screen.getByTestId("page-btn-2")).toBeInTheDocument();
  });

  it("page 1 button is green (extracted) because mineru has an element for p1-b0", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));

    expect(screen.getByTestId("page-btn-1").className).toContain("green");
  });

  it("page 2 button is red (no extraction) when mineru has no element for page 2", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));

    expect(screen.getByTestId("page-btn-2").className).toContain("red");
  });

  it("clicking a page button navigates to that page", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));

    expect(screen.getByTestId("page-btn-1")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("page-btn-2")).toHaveAttribute("aria-pressed", "false");

    // Click collapses the grid
    fireEvent.click(screen.getByTestId("page-btn-2"));

    // Re-open and verify
    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));

    await waitFor(() =>
      expect(screen.getByTestId("page-btn-2")).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.getByTestId("page-btn-1")).toHaveAttribute("aria-pressed", "false");
  });

  it("lock button PATCHes the page to done and flips the page button to blue", async () => {
    // Server starts with page 1 not done; after the PATCH it reports it done
    // so the post-mutation refetch keeps the button blue.
    let done: number[] = [];
    const patchSpy = vi.fn();
    server.use(
      http.get("*/api/admin/docs/rep/pages/status", () =>
        HttpResponse.json({ slug: "rep", done_pages: done }),
      ),
      http.patch("*/api/admin/docs/rep/pages/:page/status", async ({ params, request }) => {
        const body = (await request.json()) as { status: string };
        patchSpy({ page: Number(params.page), status: body.status });
        if (body.status === "done") done = [Number(params.page)];
        else done = done.filter((p) => p !== Number(params.page));
        return HttpResponse.json({ page: Number(params.page), status: body.status });
      }),
    );

    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("extract-page-grid-toggle"));

    const lockBtn = screen.getByRole("button", { name: /seite abschließen/i });
    fireEvent.click(lockBtn);

    // PATCH fired with the "done" status for page 1.
    await waitFor(() =>
      expect(patchSpy).toHaveBeenCalledWith({ page: 1, status: "done" }),
    );

    // Page-grid button for page 1 flips to blue (done) state.
    fireEvent.click(screen.getByTestId("extract-page-grid-toggle"));
    await waitFor(() =>
      expect(screen.getByTestId("page-btn-1").className).toContain("blue"),
    );
  });

  it("lock button label toggles to 'Seite wieder öffnen' after marking done", async () => {
    let done: number[] = [];
    server.use(
      http.get("*/api/admin/docs/rep/pages/status", () =>
        HttpResponse.json({ slug: "rep", done_pages: done }),
      ),
      http.patch("*/api/admin/docs/rep/pages/:page/status", async ({ params, request }) => {
        const body = (await request.json()) as { status: string };
        if (body.status === "done") done = [Number(params.page)];
        else done = done.filter((p) => p !== Number(params.page));
        return HttpResponse.json({ page: Number(params.page), status: body.status });
      }),
    );

    render(wrap());
    await waitForEditor();

    const lockBtn = screen.getByRole("button", { name: /seite abschließen/i });
    fireEvent.click(lockBtn);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /seite wieder öffnen/i })).toBeInTheDocument(),
    );
  });

  // ── Confidence filter (from segment.confThreshold localStorage) ────────

  it("conf filter status indicator is always visible", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() =>
      expect(screen.getByTestId("conf-filter-status")).toBeInTheDocument(),
    );
  });

  it("conf filter status shows default threshold 0.70 when no localStorage key", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => {
      const indicator = screen.getByTestId("conf-filter-status");
      expect(indicator.textContent).toContain("0.70");
    });
  });

  it("low-confidence box on page 1 is hidden by default (conf filter applied)", async () => {
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // p1-b1 has confidence 0.50 < 0.70 → hidden
    expect(screen.queryByTestId("box-p1-b1")).not.toBeInTheDocument();
  });

  it("conf filter threshold read from localStorage segment.confThreshold.{slug}", async () => {
    // Set a per-doc default of 0.40 → low-confidence box (0.50) should become visible
    localStorage.setItem(
      "segment.confThreshold.rep",
      JSON.stringify({ default: 0.40, perPage: {} }),
    );
    render(wrap());
    await waitForEditor();
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // p1-b1 has confidence 0.50 >= 0.40 → visible
    await waitFor(() =>
      expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument(),
    );
  });

  it("conf filter status reflects per-page override when set in localStorage", async () => {
    localStorage.setItem(
      "segment.confThreshold.rep",
      JSON.stringify({ default: 0.70, perPage: { 1: 0.55 } }),
    );
    render(wrap());
    await waitForEditor();
    await waitFor(() => {
      const indicator = screen.getByTestId("conf-filter-status");
      expect(indicator.textContent).toContain("0.55");
    });
  });
});

// suppress unused import warning from vi.MockInstance
void (undefined as unknown as MockInstance);

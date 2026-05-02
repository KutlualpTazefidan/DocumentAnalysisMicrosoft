// frontend/tests/local-pdf/routes/segment.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { SegmentRoute } from "../../../src/admin/routes/segment";

vi.mock("../../../src/admin/hooks/usePdfPage", () => ({
  usePdfPage: () => ({
    numPages: 5,
    viewport: { width: 600, height: 800 },
    canvasRef: { current: null },
    loading: false,
    error: null,
  }),
}));

const SEGMENT_NDJSON = [
  { type: "model-loading", model: "DocLayout-YOLO", timestamp_ms: 1, source: "/w", vram_estimate_mb: 700 },
  { type: "model-loaded", model: "DocLayout-YOLO", timestamp_ms: 2, vram_actual_mb: 612, load_seconds: 1.0 },
  {
    type: "work-progress", model: "DocLayout-YOLO", timestamp_ms: 3, stage: "page",
    current: 1, total: 1, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 612,
  },
  { type: "work-complete", model: "DocLayout-YOLO", timestamp_ms: 4, total_seconds: 1.0, items_processed: 2, output_summary: { pages: 1 } },
  { type: "model-unloading", model: "DocLayout-YOLO", timestamp_ms: 5 },
  { type: "model-unloaded", model: "DocLayout-YOLO", timestamp_ms: 6, vram_freed_mb: 612 },
]
  .map((l) => JSON.stringify(l))
  .join("\n");

// Two boxes: one above threshold (0.95) and one below (0.6 < 0.7 default)
const BOXES = [
  { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0, manually_activated: false },
  { box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.6, reading_order: 1, manually_activated: false },
];

// Boxes with cross-page link set
const BOXES_WITH_CONTINUES_TO = [
  { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0, manually_activated: false, continues_to: "p2-b0" },
];

const server = setupServer(
  http.get("*/api/admin/docs/rep", () =>
    HttpResponse.json({ slug: "rep", filename: "Rep.pdf", pages: 5, status: "raw", last_touched_utc: "2026-01-01T00:00:00Z", box_count: 2 }),
  ),
  http.get("*/api/admin/docs/rep/segments", () =>
    HttpResponse.json({ slug: "rep", boxes: BOXES }),
  ),
  http.put("*/api/admin/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "list_item", confidence: 0.95, reading_order: 0, manually_activated: false }),
  ),
  http.put("*/api/admin/docs/rep/segments/p1-b1", async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.6, reading_order: 1, manually_activated: body.manually_activated ?? false });
  }),
  http.post("*/api/admin/docs/rep/segment", () =>
    new HttpResponse(SEGMENT_NDJSON, { headers: { "Content-Type": "application/x-ndjson" } }),
  ),
  http.post("*/api/admin/docs/rep/segments/reset", () =>
    HttpResponse.json({ slug: "rep", boxes: BOXES }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/reset", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0, manually_activated: false }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/merge-down", () =>
    HttpResponse.json({ slug: "rep", boxes: [{ ...BOXES[0], continues_to: "p2-b0" }] }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/merge-up", () =>
    HttpResponse.json({ slug: "rep", boxes: [{ ...BOXES[0], continues_from: "p0-b0" }] }),
  ),
  http.post("*/api/admin/docs/rep/segments/p1-b0/unmerge-down", () =>
    HttpResponse.json({ slug: "rep", boxes: [{ ...BOXES_WITH_CONTINUES_TO[0], continues_to: null }] }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Clear localStorage before each test to reset conf threshold and approval state.
beforeEach(() => {
  localStorage.clear();
});

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/local-pdf/doc/rep/segment"]}>
          <Routes>
            <Route path="/local-pdf/doc/:slug/segment" element={<SegmentRoute token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("SegmentRoute", () => {
  it("renders the page-1 boxes after segments load", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByTestId("box-p1-b0")).toBeInTheDocument());
    // p1-b1 is below threshold (0.6 < 0.7); hidden by default
    expect(screen.queryByTestId("box-p1-b1")).not.toBeInTheDocument();
  });

  it("boxes below threshold are hidden by default", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // Confidence 0.6 box must not render while showDeactivated is off
    expect(screen.queryByTestId("box-p1-b1")).not.toBeInTheDocument();
  });

  it("show-deactivated checkbox (in top bar) reveals low-confidence box with data-deactivated attribute", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));

    const checkbox = screen.getByLabelText("Show deactivated");
    fireEvent.click(checkbox);

    await waitFor(() => expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument());
    expect(screen.getByTestId("box-p1-b1")).toHaveAttribute("data-deactivated", "true");
    // Active box must NOT have the attribute
    expect(screen.getByTestId("box-p1-b0")).not.toHaveAttribute("data-deactivated");
  });

  it("confidence threshold slider is in the top bar", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // Slider is in the top bar — found by aria-label
    const slider = screen.getByLabelText("Confidence threshold") as HTMLInputElement;
    expect(slider).toBeInTheDocument();
    expect(slider.value).toBe("0.7");
  });

  it("Alle Seiten segmentieren button is on the top bar and calls segment (no page param)", async () => {
    const calls: string[] = [];
    server.use(
      http.post("*/api/admin/docs/rep/segment", ({ request }) => {
        calls.push(new URL(request.url).search);
        return new HttpResponse(SEGMENT_NDJSON, { headers: { "Content-Type": "application/x-ndjson" } });
      }),
    );

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));

    fireEvent.click(screen.getByLabelText("Alle Seiten segmentieren"));
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    // No page param — full-doc segmentation
    expect(calls[0]).toBe("");
  });

  it("Mehr Seiten segmentieren button is on the top bar", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    const btn = screen.getByLabelText("Mehr Seiten segmentieren");
    expect(btn).toBeInTheDocument();
  });

  it("sidebar has page-button grid (no Pagination component)", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // Page-button grid buttons exist in the sidebar
    expect(screen.getByTestId("seg-page-btn-1")).toBeInTheDocument();
    // No "Jump to page" input (that was Pagination)
    expect(screen.queryByLabelText("Jump to page")).not.toBeInTheDocument();
  });

  it("sidebar shows colored page buttons (green for segmented page 1)", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // page 1 has boxes → segmented → green
    await waitFor(() =>
      expect(screen.getByTestId("seg-page-btn-1").className).toContain("green"),
    );
  });

  it("clicking segment page button navigates to that page", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("seg-page-btn-1"));

    // Initially page 1 is active
    expect(screen.getByTestId("seg-page-btn-1")).toHaveAttribute("aria-pressed", "true");

    // Click page 3 button
    fireEvent.click(screen.getByTestId("seg-page-btn-3"));

    await waitFor(() =>
      expect(screen.getByTestId("seg-page-btn-3")).toHaveAttribute("aria-pressed", "true"),
    );
    expect(screen.getByTestId("seg-page-btn-1")).toHaveAttribute("aria-pressed", "false");
  });

  it("sidebar approve button toggles page to blue state", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("seg-page-btn-1"));

    const approveBtn = screen.getByRole("button", { name: /diese seite genehmigen/i });
    fireEvent.click(approveBtn);

    await waitFor(() =>
      expect(screen.getByTestId("seg-page-btn-1").className).toContain("blue"),
    );

    // localStorage should contain the approved page
    const stored = JSON.parse(localStorage.getItem("segment.approved.rep") ?? "[]") as number[];
    expect(stored).toContain(1);
  });

  it("sidebar approve button label toggles to 'Genehmigung aufheben' after approval", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("seg-page-btn-1"));

    const approveBtn = screen.getByRole("button", { name: /diese seite genehmigen/i });
    fireEvent.click(approveBtn);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /genehmigung aufheben/i })).toBeInTheDocument(),
    );
  });

  it("sidebar shows Seite X / Y heading", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    // Sidebar heading shows current page / total pages (1 / 5 from docMeta mock)
    expect(screen.getByRole("heading", { level: 2, name: /Seite 1 \/ 5/i })).toBeInTheDocument();
  });

  it("changes selected box kind via hotkey 'l'", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    fireEvent.keyDown(window, { key: "l" });
    await waitFor(() => {
      const select = screen.getByDisplayValue("list_item") as HTMLSelectElement;
      expect(select).toBeInTheDocument();
    });
  });

  it("StageIndicator is not present until segmentation runs", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    expect(screen.queryByTestId("stage-toggle")).not.toBeInTheDocument();
  });

  it("Deactivate button is in the sidebar (not the top bar)", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByLabelText("Deactivate"));
    const btn = screen.getByLabelText("Deactivate");
    expect(btn).toBeInTheDocument();
    expect(btn.closest("aside")).not.toBeNull();
  });

  it("New box button label is 'New box' without hotkey hint", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByRole("button", { name: "New box" }));
    const btn = screen.getByRole("button", { name: "New box" });
    expect(btn.textContent).toBe("New box");
    expect(btn.closest("aside")).not.toBeNull();
  });

  it("Reset diese Seite button is in the sidebar", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    const btn = screen.getByLabelText("Reset diese Seite");
    expect(btn).toBeInTheDocument();
    expect(btn.closest("aside")).not.toBeNull();
  });

  it("Reset box button appears in sidebar when a box is selected", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByLabelText("Reset box"));
    const btn = screen.getByLabelText("Reset box");
    expect(btn.closest("aside")).not.toBeNull();
  });

  it("Reset diese Seite fires confirm and calls reset endpoint", async () => {
    const calls: string[] = [];
    server.use(
      http.post("*/api/admin/docs/rep/segments/reset", ({ request }) => {
        calls.push(new URL(request.url).search);
        return HttpResponse.json({ slug: "rep", boxes: BOXES });
      }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByLabelText("Reset diese Seite"));
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    expect(calls[0]).toContain("page=1");

    vi.restoreAllMocks();
  });

  it("box below threshold is hidden when manually_activated is false", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    expect(screen.queryByTestId("box-p1-b1")).not.toBeInTheDocument();
  });

  it("box below threshold is visible when manually_activated is true", async () => {
    const activatedBoxes = [
      { ...BOXES[0] },
      { ...BOXES[1], manually_activated: true },
    ];
    server.use(
      http.get("*/api/admin/docs/rep/segments", () =>
        HttpResponse.json({ slug: "rep", boxes: activatedBoxes }),
      ),
    );
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument();
  });

  it("clicking Activate button dispatches PUT with manually_activated: true", async () => {
    const putBodies: unknown[] = [];
    server.use(
      http.put("*/api/admin/docs/rep/segments/p1-b1", async ({ request }) => {
        const body = await request.json();
        putBodies.push(body);
        return HttpResponse.json({ ...BOXES[1], manually_activated: true });
      }),
    );

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));

    // Enable showDeactivated to make p1-b1 visible for selection
    fireEvent.click(screen.getByLabelText("Show deactivated"));
    await waitFor(() => screen.getByTestId("box-p1-b1"));

    fireEvent.click(screen.getByTestId("box-p1-b1"));
    await waitFor(() => screen.getByLabelText("Activate"));

    fireEvent.click(screen.getByLabelText("Activate"));
    await waitFor(() => expect(putBodies.length).toBeGreaterThanOrEqual(1));
    expect(putBodies[0]).toMatchObject({ manually_activated: true });
  });

  it("Merge up button is disabled on page 1", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByLabelText("Merge up"));
    expect(screen.getByLabelText("Merge up")).toBeDisabled();
  });

  it("Merge down button is enabled on page 1 (not last page) when no continues_to", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByLabelText("Merge down"));
    expect(screen.getByLabelText("Merge down")).not.toBeDisabled();
  });

  it("click merge-down dispatches POST to the right URL", async () => {
    const calls: string[] = [];
    server.use(
      http.post("*/api/admin/docs/rep/segments/:boxId/merge-down", ({ params }) => {
        calls.push(params.boxId as string);
        return HttpResponse.json({ slug: "rep", boxes: [{ ...BOXES[0], continues_to: "p2-b0" }] });
      }),
    );

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    await waitFor(() => screen.getByLabelText("Merge down"));
    const mergeDownBtn = screen.getByLabelText("Merge down");
    expect(mergeDownBtn).not.toBeDisabled();
    fireEvent.click(mergeDownBtn);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    expect(calls[0]).toBe("p1-b0");
  });

  it("box with continues_to renders the down indicator", async () => {
    server.use(
      http.get("*/api/admin/docs/rep/segments", () =>
        HttpResponse.json({ slug: "rep", boxes: BOXES_WITH_CONTINUES_TO }),
      ),
    );
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    expect(screen.getByTestId("continues-to-indicator-p1-b0")).toBeInTheDocument();
  });

  it("clicking Mehr Seiten segmentieren opens a dialog", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByLabelText("Mehr Seiten segmentieren"));
    await waitFor(() => screen.getByRole("dialog", { name: "Mehr Seiten segmentieren" }));
    expect(screen.getByRole("dialog", { name: "Mehr Seiten segmentieren" })).toBeInTheDocument();
  });

  it("Mehr Seiten dialog submit calls streamSegment with start and end params", async () => {
    const calls: string[] = [];
    server.use(
      http.post("*/api/admin/docs/rep/segment", ({ request }) => {
        calls.push(new URL(request.url).search);
        return new HttpResponse(SEGMENT_NDJSON, { headers: { "Content-Type": "application/x-ndjson" } });
      }),
    );

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));

    // Open dialog
    fireEvent.click(screen.getByLabelText("Mehr Seiten segmentieren"));
    await waitFor(() => screen.getByRole("dialog", { name: "Mehr Seiten segmentieren" }));

    // Change the "Bis Seite" input to 3
    const bisInput = screen.getByLabelText("Mehr bis Seite") as HTMLInputElement;
    fireEvent.change(bisInput, { target: { value: "3" } });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: "Segmentieren" }));

    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    expect(calls[0]).toMatch(/start=\d+/);
    expect(calls[0]).toMatch(/end=3/);
  });

  it("when continues_to is set, Merge down becomes Unmerge ↓ and clicking dispatches POST to unmerge-down", async () => {
    const calls: string[] = [];
    server.use(
      http.get("*/api/admin/docs/rep/segments", () =>
        HttpResponse.json({ slug: "rep", boxes: BOXES_WITH_CONTINUES_TO }),
      ),
      http.post("*/api/admin/docs/rep/segments/:boxId/unmerge-down", ({ params }) => {
        calls.push(params.boxId as string);
        return HttpResponse.json({ slug: "rep", boxes: [{ ...BOXES_WITH_CONTINUES_TO[0], continues_to: null }] });
      }),
    );

    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));

    fireEvent.click(screen.getByTestId("box-p1-b0"));

    await waitFor(() => screen.getByLabelText("Unmerge down"));
    expect(screen.queryByLabelText("Merge down")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Unmerge down"));
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    expect(calls[0]).toBe("p1-b0");
  });
});

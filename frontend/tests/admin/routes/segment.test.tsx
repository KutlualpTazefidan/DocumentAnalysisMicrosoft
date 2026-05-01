// frontend/tests/local-pdf/routes/segment.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { SegmentRoute } from "../../../src/admin/routes/segment";

vi.mock("../../../src/admin/hooks/usePdfPage", () => ({
  usePdfPage: () => ({
    numPages: 2,
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

const server = setupServer(
  http.get("*/api/admin/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
        { box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.6, reading_order: 1 },
      ],
    }),
  ),
  http.put("*/api/admin/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "list_item", confidence: 0.95, reading_order: 0 }),
  ),
  http.post("*/api/admin/docs/rep/segment", () =>
    new HttpResponse(SEGMENT_NDJSON, { headers: { "Content-Type": "application/x-ndjson" } }),
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
    expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument();
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
});

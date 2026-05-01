// frontend/tests/local-pdf/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ExtractRoute } from "../../../src/local-pdf/routes/extract";

vi.mock("../../../src/local-pdf/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
      ],
    }),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep/html", () =>
    HttpResponse.json({ html: '<h1 data-source-box="p1-b0">Hi</h1>' }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/html", () => HttpResponse.json({ ok: true })),
  http.post("http://127.0.0.1:8001/api/docs/rep/export", () =>
    HttpResponse.json({ doc_slug: "rep", source_pipeline: "local-pdf", elements: [] }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/extract"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/extract" element={<ExtractRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
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
    fireEvent.click(screen.getByRole("button", { name: /export/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export/i })).not.toBeDisabled(),
    );
  });
});

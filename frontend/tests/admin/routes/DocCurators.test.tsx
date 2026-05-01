// frontend/tests/admin/routes/DocCurators.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { DocCurators } from "../../../src/admin/routes/DocCurators";

const ALL_CURATORS = [
  { id: "c1", name: "Dr Müller", token_prefix: "abc123", created_utc: "2026-04-01T10:00:00Z" },
  { id: "c2", name: "Dr Weber", token_prefix: "def456", created_utc: "2026-04-02T10:00:00Z" },
];

const DOC_CURATORS_INITIAL: typeof ALL_CURATORS = [];

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/admin/curators", () =>
    HttpResponse.json(ALL_CURATORS),
  ),
  http.get("http://127.0.0.1:8001/api/admin/docs/:slug/curators", () =>
    HttpResponse.json(DOC_CURATORS_INITIAL),
  ),
  http.post("http://127.0.0.1:8001/api/admin/docs/:slug/curators", async ({ request }) => {
    const body = (await request.json()) as { curator_id: string };
    const matched = ALL_CURATORS.find((c) => c.id === body.curator_id);
    if (!matched) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(matched, { status: 201 });
  }),
  http.delete("http://127.0.0.1:8001/api/admin/docs/:slug/curators/:curatorId", () =>
    new HttpResponse(null, { status: 204 }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped(slug = "my-doc") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/admin/doc/${slug}/curators`]}>
          <Routes>
            <Route path="/admin/doc/:slug/curators" element={<DocCurators token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("DocCurators", () => {
  it("loads /admin/doc/<slug>/curators and shows all-curators picker", async () => {
    render(wrapped("my-doc"));
    await waitFor(() => expect(screen.getByText("Dr Müller")).toBeInTheDocument());
    expect(screen.getByText("Dr Weber")).toBeInTheDocument();
  });

  it("clicking + assign sends POST /api/admin/docs/<slug>/curators with curator_id, table re-renders", async () => {
    let postReceived = false;

    // Override: POST marks assignment done; subsequent GET returns the assigned curator
    server.use(
      http.get("http://127.0.0.1:8001/api/admin/docs/my-doc/curators", () => {
        if (postReceived) {
          return HttpResponse.json([ALL_CURATORS[0]]);
        }
        return HttpResponse.json([]);
      }),
      http.post("http://127.0.0.1:8001/api/admin/docs/my-doc/curators", async ({ request }) => {
        const body = (await request.json()) as { curator_id: string };
        postReceived = true;
        const matched = ALL_CURATORS.find((c) => c.id === body.curator_id);
        if (!matched) return new HttpResponse(null, { status: 404 });
        return HttpResponse.json(matched, { status: 201 });
      }),
    );

    render(wrapped("my-doc"));

    // Wait for Dr Müller to appear in the all-curators picker (left pane)
    await waitFor(() => expect(screen.getAllByText("Dr Müller").length).toBeGreaterThanOrEqual(1));

    // Find and click the "+ assign" button next to Dr Müller
    const assignButton = await screen.findByRole("button", { name: /assign Dr Müller/i });
    fireEvent.click(assignButton);

    // After re-fetch, Dr Müller should appear in the right pane too (2 total)
    await waitFor(() => {
      expect(screen.getAllByText("Dr Müller").length).toBeGreaterThanOrEqual(2);
    });
  });
});

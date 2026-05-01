// frontend/tests/local-pdf/routes/inbox.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { InboxRoute } from "../../../src/admin/routes/inbox";

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/admin/docs", () =>
    HttpResponse.json([
      { slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 },
      { slug: "spec", filename: "Spec.pdf", pages: 12, status: "done", last_touched_utc: "2026-04-30T11:00:00Z", box_count: 35 },
    ]),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/inbox"]}>
        <Routes>
          <Route path="/local-pdf/inbox" element={<InboxRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("InboxRoute", () => {
  it("lists docs with status badge", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Rep.pdf")).toBeInTheDocument());
    expect(screen.getByText("Spec.pdf")).toBeInTheDocument();
    expect(screen.getByText("raw")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  it("filters by search input", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Rep.pdf")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "spec" } });
    expect(screen.queryByText("Rep.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Spec.pdf")).toBeInTheDocument();
  });

  it("renders Add PDF button", async () => {
    render(wrapped());
    expect(screen.getByRole("button", { name: /add pdf/i })).toBeInTheDocument();
  });
});

import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CuratorDocPage } from "../../../src/curator/routes/DocPage";
import { ToastProvider } from "../../../src/shared/components/Toaster";

vi.mock("../../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "T", role: "curator", name: "Q" }),
}));

let postedBody: unknown = null;
const server = setupServer(
  http.get("http://127.0.0.1:8001/api/curate/docs/doc-a/elements", () =>
    HttpResponse.json([
      { element_id: "p1-x", page_number: 1, element_type: "paragraph", content: "Foo" },
    ])
  ),
  http.post("http://127.0.0.1:8001/api/curate/docs/doc-a/questions", async ({ request }) => {
    postedBody = await request.json();
    return new HttpResponse(JSON.stringify({
      question_id: "q-1", element_id: "p1-x", curator_id: "c-1",
      query: (postedBody as { query: string }).query, created_at: "t",
    }), { status: 201 });
  }),
);
beforeAll(() => server.listen());
afterEach(() => { server.resetHandlers(); postedBody = null; });
afterAll(() => server.close());

describe("CuratorDocPage", () => {
  it("posts a question for an element", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <MemoryRouter initialEntries={["/curate/doc/doc-a"]}>
            <Routes>
              <Route path="/curate/doc/:slug/element/:elementId" element={<CuratorDocPage />} />
              <Route path="/curate/doc/:slug" element={<CuratorDocPage />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("Foo");
    await userEvent.type(screen.getByPlaceholderText(/Frage/i), "Was bedeutet Foo?");
    await userEvent.click(screen.getByRole("button", { name: /Senden|Hinzufügen/i }));
    await waitFor(() =>
      expect(postedBody).toEqual({ element_id: "p1-x", query: "Was bedeutet Foo?" })
    );
  });

  it("j moves to next element via deep-link navigation", async () => {
    const qc = new QueryClient();
    server.use(
      http.get("http://127.0.0.1:8001/api/curate/docs/doc-a/elements", () =>
        HttpResponse.json([
          { element_id: "p1-x", page_number: 1, element_type: "paragraph", content: "Foo" },
          { element_id: "p1-y", page_number: 1, element_type: "paragraph", content: "Bar" },
        ])
      ),
    );
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <MemoryRouter initialEntries={["/curate/doc/doc-a/element/p1-x"]}>
            <Routes>
              <Route path="/curate/doc/:slug/element/:elementId" element={<CuratorDocPage />} />
              <Route path="/curate/doc/:slug" element={<CuratorDocPage />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("Foo");
    await userEvent.keyboard("j");
    await waitFor(() => expect(screen.getByText("Bar")).toBeInTheDocument());
  });
});

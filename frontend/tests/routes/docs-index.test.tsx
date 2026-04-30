import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { DocsIndex } from "../../src/routes/docs-index";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderDocs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/docs"]}>
        <Routes>
          <Route path="/docs" element={<DocsIndex />} />
          <Route
            path="/docs/:slug/elements"
            element={<div>Element page for {/* slug */}</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DocsIndex", () => {
  it("lists docs returned by GET /api/docs", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([
          { slug: "smoke-test-tragkorb", element_count: 9 },
          { slug: "another-doc", element_count: 47 },
        ]),
      ),
    );
    renderDocs();
    expect(await screen.findByText("smoke-test-tragkorb")).toBeInTheDocument();
    expect(screen.getByText(/9 elements/i)).toBeInTheDocument();
    expect(screen.getByText("another-doc")).toBeInTheDocument();
  });

  it("shows empty-state when no docs", async () => {
    server.use(
      http.get("http://localhost/api/docs", () => HttpResponse.json([])),
    );
    renderDocs();
    expect(
      await screen.findByText(/keine dokumente|no documents/i),
    ).toBeInTheDocument();
  });

  it("clicking a doc navigates to its elements page", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([{ slug: "doc-x", element_count: 3 }]),
      ),
    );
    const user = userEvent.setup();
    renderDocs();
    const link = await screen.findByRole("link", { name: /doc-x/i });
    await user.click(link);
    expect(await screen.findByText(/element page for/i)).toBeInTheDocument();
  });
});

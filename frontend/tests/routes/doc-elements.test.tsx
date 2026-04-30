import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { DocElements } from "../../src/routes/doc-elements";

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

const elements = [
  {
    element: {
      element_id: "p1-aaa",
      page_number: 1,
      element_type: "heading",
      content: "First",
    },
    count_active_entries: 0,
  },
  {
    element: {
      element_id: "p1-bbb",
      page_number: 1,
      element_type: "paragraph",
      content: "Second body.",
    },
    count_active_entries: 1,
  },
];

function renderRoute(initial = "/docs/foo/elements") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/docs/:slug/elements" element={<DocElements />} />
          <Route path="/docs/:slug/elements/:elementId" element={<DocElements />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DocElements route", () => {
  it("renders sidebar + first element selected when no :elementId in URL", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json(elements),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({ element: elements[0].element, entries: [] }),
      ),
    );
    renderRoute();
    // "First" appears in both sidebar row and element-body
    const matches = await screen.findAllByText("First");
    expect(matches.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText(/noch keine fragen/i)).toBeInTheDocument();
  });

  it("Weiter button advances to next element_id", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json(elements),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({ element: elements[0].element, entries: [] }),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-bbb", () =>
        HttpResponse.json({ element: elements[1].element, entries: [] }),
      ),
    );
    const user = userEvent.setup();
    renderRoute("/docs/foo/elements/p1-aaa");
    await screen.findAllByText("First");
    await user.click(screen.getByRole("button", { name: /weiter/i }));
    const secondMatches = await screen.findAllByText(/second body/i);
    expect(secondMatches.length).toBeGreaterThanOrEqual(1);
  });
});

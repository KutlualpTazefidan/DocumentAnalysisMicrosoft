import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CuratorDocs } from "../../../src/curator/routes/Docs";

vi.mock("../../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "T", role: "curator", name: "Q", logout: () => {} }),
}));

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/curate/docs", () =>
    HttpResponse.json([
      { slug: "doc-a", filename: "doc-a.pdf", pages: 3, status: "open-for-curation",
        last_touched_utc: "t", box_count: 5 },
    ])
  ),
);
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("CuratorDocs", () => {
  it("lists assigned docs", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><CuratorDocs /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("doc-a.pdf")).toBeInTheDocument();
  });
});

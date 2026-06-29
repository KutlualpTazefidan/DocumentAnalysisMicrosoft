import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { Knowledge } from "../Knowledge";

vi.mock("../../../auth/useAuth", () => ({ useAuth: () => ({ token: "tok" }) }));

const bam = {
  path: "behoerden/bam.md", type: "Behörde", title: "BAM",
  description: "", timestamp: "", tags: ["behoerde"],
  body: "Die BAM prüft.", malformed: false,
  links: [{ text: "Nachweiskonzept", path: "konzepte/nachweiskonzept.md", resolved: true }],
};
const nachweis = {
  path: "konzepte/nachweiskonzept.md", type: "Konzept", title: "Nachweiskonzept",
  description: "", timestamp: "", tags: [], body: "Basis der Analysen.",
  malformed: false, links: [],
};

const server = setupServer(
  http.get("*/api/admin/knowledge/bases", () =>
    HttpResponse.json([{ name: "bauartpruefung-lm", title: "Bauartprüfung", concept_count: 2 }])
  ),
  http.get("*/api/admin/knowledge/bases/:base/concepts", () =>
    HttpResponse.json([
      { path: bam.path, type: bam.type, title: bam.title, tags: bam.tags },
      { path: nachweis.path, type: nachweis.type, title: nachweis.title, tags: [] },
    ])
  ),
  http.get("*/api/admin/knowledge/bases/:base/concept", ({ request }) => {
    const p = new URL(request.url).searchParams.get("path");
    return HttpResponse.json(p === nachweis.path ? nachweis : bam);
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Knowledge token="tok" />
    </QueryClientProvider>
  );
}

describe("Wissen (Knowledge) tab", () => {
  it("lists concepts and walks an outgoing link", async () => {
    renderPage();
    // concept list renders
    await waitFor(() => expect(screen.getByText("BAM")).toBeInTheDocument());
    // open BAM
    await userEvent.click(screen.getByText("BAM"));
    await waitFor(() => expect(screen.getByText("Die BAM prüft.")).toBeInTheDocument());
    // walk the graph: click the outgoing link in the main pane → target concept loads
    // (scope to <main> to distinguish outgoing link from sidebar concept-list button)
    await userEvent.click(within(screen.getByRole("main")).getByRole("button", { name: /Nachweiskonzept/ }));
    await waitFor(() => expect(screen.getByText("Basis der Analysen.")).toBeInTheDocument());
  });
});

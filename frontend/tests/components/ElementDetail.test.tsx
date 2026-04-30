import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { ElementDetail } from "../../src/components/ElementDetail";

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

function renderDetail(props: { slug: string; elementId: string; onWeiter?: () => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ElementDetail
          slug={props.slug}
          elementId={props.elementId}
          onWeiter={props.onWeiter ?? (() => {})}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ElementDetail", () => {
  it("renders element body, entries list, new-entry-form, weiter button", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({
          element: {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "paragraph",
            content: "Body text.",
          },
          entries: [
            {
              entry_id: "e_001",
              query: "Was steht hier?",
              expected_chunk_ids: [],
              chunk_hashes: {},
              review_chain: [
                {
                  timestamp_utc: "2026-04-30T07:00Z",
                  action: "created_from_scratch",
                  actor: { kind: "human", pseudonym: "alice", level: "phd" },
                  notes: null,
                },
              ],
              deprecated: false,
              refines: null,
              task_type: "retrieval",
              source_element: null,
            },
          ],
        }),
      ),
    );
    renderDetail({ slug: "foo", elementId: "p1-aaa" });
    expect(await screen.findByText("Body text.")).toBeInTheDocument();
    expect(screen.getByText(/was steht hier/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/neue frage/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /weiter/i })).toBeInTheDocument();
  });
});

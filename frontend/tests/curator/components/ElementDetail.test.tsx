import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../../../src/shared/components/Toaster";
import { ElementDetail } from "../../../src/curator/components/ElementDetail";

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
      <ToastProvider>
        <MemoryRouter>
          <ElementDetail
            slug={props.slug}
            elementId={props.elementId}
            onWeiter={props.onWeiter ?? (() => {})}
          />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ElementDetail", () => {
  it("renders element body, entries list, new-entry-form, weiter button", async () => {
    server.use(
      http.get("http://localhost/api/curate/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({
          element_id: "p1-aaa",
          page_number: 1,
          element_type: "paragraph",
          content: "Body text.",
        }),
      ),
      http.get("http://localhost/api/curate/docs/foo/questions", () =>
        HttpResponse.json([
          {
            question_id: "q-001",
            element_id: "p1-aaa",
            curator_id: "c-alice",
            query: "Was steht hier?",
            refined_query: null,
            deprecated: false,
            deprecated_reason: null,
            created_at: "2026-04-30T07:00Z",
          },
        ]),
      ),
    );
    renderDetail({ slug: "foo", elementId: "p1-aaa" });
    expect(await screen.findByText("Body text.")).toBeInTheDocument();
    expect(screen.getByText(/was steht hier/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/neue frage/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /weiter/i })).toBeInTheDocument();
  });
});

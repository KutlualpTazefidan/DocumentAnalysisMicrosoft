import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { EntryRefineModal } from "../../src/components/EntryRefineModal";
import type { RetrievalEntry } from "../../src/types/domain";

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

const entry: RetrievalEntry = {
  entry_id: "e_001",
  query: "Original frage",
  expected_chunk_ids: [],
  chunk_hashes: {},
  review_chain: [],
  deprecated: false,
  refines: null,
  task_type: "retrieval",
  source_element: null,
};

function renderModal(props: { onClose?: () => void; slug?: string; elementId?: string }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EntryRefineModal
        entry={entry}
        slug={props.slug ?? "doc-x"}
        elementId={props.elementId ?? "p1-aaa"}
        onClose={props.onClose ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe("EntryRefineModal", () => {
  it("prefills the query with the entry's existing query", () => {
    renderModal({});
    expect(screen.getByLabelText(/neue frage/i)).toHaveValue("Original frage");
  });

  it("submits refine and closes on success", async () => {
    server.use(
      http.post("http://localhost/api/entries/e_001/refine", () =>
        HttpResponse.json({ new_entry_id: "e_002" }),
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderModal({ onClose });
    const ta = screen.getByLabelText(/neue frage/i);
    await user.clear(ta);
    await user.type(ta, "Verbesserte frage");
    await user.click(screen.getByRole("button", { name: /verfeinern/i }));
    await screen.findByText(/verfeinert/i, undefined, { timeout: 2000 }).catch(() => {});
    expect(onClose).toHaveBeenCalled();
  });

  it("Escape key closes the modal", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderModal({ onClose });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});

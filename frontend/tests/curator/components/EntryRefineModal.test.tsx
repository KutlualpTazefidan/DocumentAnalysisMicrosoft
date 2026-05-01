import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { ToastProvider } from "../../../src/shared/components/Toaster";
import { EntryRefineModal } from "../../../src/curator/components/EntryRefineModal";
import type { CuratorQuestion } from "../../../src/curator/api/curatorClient";

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

const entry: CuratorQuestion = {
  question_id: "q-001",
  element_id: "p1-aaa",
  curator_id: "c-alice",
  query: "Original frage",
  refined_query: null,
  deprecated: false,
  deprecated_reason: null,
  created_at: "2026-04-30T07:00:00Z",
};

function renderModal(props: { onClose?: () => void; slug?: string; elementId?: string }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <EntryRefineModal
          entry={entry}
          slug={props.slug ?? "doc-x"}
          elementId={props.elementId ?? "p1-aaa"}
          onClose={props.onClose ?? (() => {})}
        />
      </ToastProvider>
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
      http.post("*/api/curate/docs/doc-x/questions/q-001/refine", () =>
        HttpResponse.json({
          question_id: "q-001",
          element_id: "p1-aaa",
          curator_id: "c-alice",
          query: "Original frage",
          refined_query: "Verbesserte frage",
          deprecated: false,
          deprecated_reason: null,
          created_at: "2026-04-30T07:00:00Z",
        }),
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

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { Toaster } from "react-hot-toast";
import { NewEntryForm } from "../../../src/curator/components/NewEntryForm";

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

function renderForm(props: Partial<{ slug: string; elementId: string; onWeiter: () => void }> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewEntryForm
        slug={props.slug ?? "doc-x"}
        elementId={props.elementId ?? "p1-aaa"}
        onWeiter={props.onWeiter ?? (() => {})}
      />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("NewEntryForm", () => {
  it("submits the typed query and clears textarea on success", async () => {
    server.use(
      http.post(
        "http://localhost/api/docs/doc-x/elements/p1-aaa/entries",
        async ({ request }) => {
          const body = (await request.json()) as { query: string };
          expect(body.query).toBe("Welche Norm gilt?");
          return HttpResponse.json(
            { entry_id: "e_abc", event_id: "ev_xyz" },
            { status: 201 },
          );
        },
      ),
    );
    const user = userEvent.setup();
    renderForm();
    const ta = screen.getByLabelText(/neue frage/i);
    await user.type(ta, "Welche Norm gilt?");
    await user.click(screen.getByRole("button", { name: /speichern/i }));
    expect(await screen.findByText(/gespeichert/i)).toBeInTheDocument();
    expect(ta).toHaveValue("");
  });

  it("calls onWeiter when textarea is empty and Enter pressed", async () => {
    let weiterCalled = false;
    const user = userEvent.setup();
    renderForm({ onWeiter: () => (weiterCalled = true) });
    const ta = screen.getByLabelText(/neue frage/i);
    ta.focus();
    await user.keyboard("{Enter}");
    expect(weiterCalled).toBe(true);
  });

  it("submits on Ctrl+Enter when textarea has content", async () => {
    server.use(
      http.post(
        "http://localhost/api/docs/doc-x/elements/p1-aaa/entries",
        () => HttpResponse.json({ entry_id: "e", event_id: "ev" }, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderForm();
    const ta = screen.getByLabelText(/neue frage/i);
    await user.type(ta, "Frage");
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(await screen.findByText(/gespeichert/i)).toBeInTheDocument();
  });
});

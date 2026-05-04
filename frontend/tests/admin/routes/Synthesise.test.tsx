// frontend/tests/admin/routes/Synthesise.test.tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { Synthesise } from "../../../src/admin/routes/Synthesise";

/**
 * New Synthesise tab — read-only HTML preview + per-box question
 * sidebar. Tests cover the shell shape: three Generate buttons, the
 * placeholder-when-no-box-selected state, the streaming cancel button
 * being absent until a stream starts, and DocStepTabs marking the
 * synthesise tab active.
 */

vi.mock("../../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "tok", role: "admin", name: "Admin" }),
}));

const server = setupServer(
  http.get("*/api/admin/docs/spec/html", () =>
    HttpResponse.json({
      html: '<html><body><section data-page="1"><p data-source-box="p1-b0">Body.</p></section></body></html>',
    }),
  ),
  http.get("*/api/admin/docs/spec/mineru", () =>
    HttpResponse.json({
      elements: [
        {
          box_id: "p1-b0",
          html_snippet: "<p>Body.</p>",
          html_snippet_raw: "<p>Body.</p>",
        },
      ],
    }),
  ),
  http.get("*/api/admin/docs/spec/questions", () => HttpResponse.json({})),
  // The mounted LlmServerPanel polls /api/admin/llm/status — return a
  // stopped state so the panel renders without errors.
  http.get("*/api/admin/llm/status", () =>
    HttpResponse.json({
      state: "stopped",
      pid: null,
      model: "Qwen/Qwen2.5-3B-Instruct",
      base_url: "http://127.0.0.1:8000/v1",
      healthy: false,
      error: null,
      log_tail: [],
      vllm_cli_available: true,
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin/doc/spec/synthesise"]}>
          <Routes>
            <Route path="/admin/doc/:slug/synthesise" element={<Synthesise />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("Synthesise", () => {
  it("renders the three Generate buttons (file/page in topbar, box in sidebar)", async () => {
    render(wrap());
    const sidebar = await screen.findByTestId("synthesise-sidebar");
    expect(sidebar).toBeInTheDocument();
    // File-scope and page-scope generate live in the second topbar.
    expect(
      screen.getByRole("button", { name: /Für die ganze Datei generieren/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Für die Seite generieren/i }),
    ).toBeInTheDocument();
    // Per-box generate stays in the right sidebar next to the metadata.
    expect(
      within(sidebar).getByRole("button", { name: /Für diese Box generieren/i }),
    ).toBeInTheDocument();
  });

  it("Per-box Generate button is disabled when no box highlighted", async () => {
    render(wrap());
    await waitFor(() =>
      expect(screen.getByTestId("synthesise-sidebar")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /Für diese Box generieren/i }),
    ).toBeDisabled();
  });

  it("shows the no-selection placeholder before any click", async () => {
    render(wrap());
    // Placeholder shows in two places now: the questions pane and the
    // sidebar's "Ausgewaehlte Box" metadata block. Both are valid.
    await waitFor(() =>
      expect(
        screen.getAllByText(/Klicke ein Element im HTML-Bereich/i).length,
      ).toBeGreaterThanOrEqual(1),
    );
  });

  it("HTML preview iframe + DocStepTabs are present", async () => {
    render(wrap());
    await waitFor(() =>
      expect(screen.getByTestId("synth-html-preview")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("tab", { name: /synthesise/i }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("Cancel button is NOT visible before a stream starts", async () => {
    render(wrap());
    await waitFor(() =>
      expect(screen.getByTestId("synthesise-sidebar")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("synthesise-cancel")).not.toBeInTheDocument();
  });
});

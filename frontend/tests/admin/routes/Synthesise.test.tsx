// frontend/tests/admin/routes/Synthesise.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { Synthesise } from "../../../src/admin/routes/Synthesise";

// Mock useAuth so Synthesise renders without a real session.
vi.mock("../../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "tok", role: "admin", name: "Admin" }),
}));

const server = setupServer(
  http.post("*/api/admin/docs/rep/synthesise/test", async ({ request }) => {
    const body = (await request.json()) as { prompt: string };
    return HttpResponse.json({
      response: `Echo: ${body.prompt}`,
      model: "qwen2.5:7b-instruct",
      elapsed_seconds: 0.42,
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  return (
    <ToastProvider>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/synthesise"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/synthesise" element={<Synthesise />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>
  );
}

describe("Synthesise", () => {
  it("renders textarea and Test LLM button", () => {
    render(wrap());
    expect(screen.getByLabelText("LLM prompt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test LLM" })).toBeInTheDocument();
  });

  it("button is disabled when prompt is empty", () => {
    render(wrap());
    expect(screen.getByRole("button", { name: "Test LLM" })).toBeDisabled();
  });

  it("button becomes enabled when prompt is typed", () => {
    render(wrap());
    fireEvent.change(screen.getByLabelText("LLM prompt"), {
      target: { value: "Summarize this" },
    });
    expect(screen.getByRole("button", { name: "Test LLM" })).not.toBeDisabled();
  });

  it("POSTs the prompt and renders the response", async () => {
    render(wrap());
    fireEvent.change(screen.getByLabelText("LLM prompt"), {
      target: { value: "Hello doc" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test LLM" }));

    await waitFor(() =>
      expect(screen.getByLabelText("LLM response")).toBeInTheDocument()
    );

    expect(screen.getByLabelText("LLM response")).toHaveTextContent("Echo: Hello doc");
    // model name + elapsed seconds should appear
    expect(screen.getByText(/qwen2\.5:7b-instruct/)).toBeInTheDocument();
    expect(screen.getByText(/0\.42s/)).toBeInTheDocument();
  });

  it("shows error toast on fetch failure", async () => {
    server.use(
      http.post("*/api/admin/docs/rep/synthesise/test", () =>
        HttpResponse.json({ detail: "LLM offline" }, { status: 503 })
      ),
    );
    render(wrap());
    fireEvent.change(screen.getByLabelText("LLM prompt"), {
      target: { value: "fail me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test LLM" }));

    // Toast appears as a status element containing the error text.
    await waitFor(() =>
      expect(screen.getByText(/503/)).toBeInTheDocument()
    );
  });
});

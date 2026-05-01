// frontend/tests/admin/routes/Curators.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ToastProvider } from "../../../src/shared/components/Toaster";
import { Curators } from "../../../src/admin/routes/Curators";

const CURATORS_INITIAL = [
  { id: "c1", name: "Dr Müller", token_prefix: "abc123", created_utc: "2026-04-01T10:00:00Z" },
];

const CREATE_RESPONSE = {
  id: "c2",
  name: "Dr X",
  token_prefix: "xyz999",
  token: "xyz999-full-secret-token",
  created_utc: "2026-04-30T10:00:00Z",
};

const server = setupServer(
  http.get("*/api/admin/curators", () =>
    HttpResponse.json(CURATORS_INITIAL),
  ),
  http.post("*/api/admin/curators", () =>
    HttpResponse.json(CREATE_RESPONSE, { status: 201 }),
  ),
  http.delete("*/api/admin/curators/:id", () =>
    new HttpResponse(null, { status: 204 }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin/curators"]}>
          <Routes>
            <Route path="/admin/curators" element={<Curators token="tok" />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("Curators", () => {
  it("lists existing curators with token_prefix", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Dr Müller")).toBeInTheDocument());
    expect(screen.getByText("abc123")).toBeInTheDocument();
  });

  it("create flow: shows full token in modal", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Dr Müller")).toBeInTheDocument());

    // Open create dialog
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    const nameInput = await screen.findByPlaceholderText(/name/i);
    fireEvent.change(nameInput, { target: { value: "Dr X" } });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    // Token shown in modal (C16: full token shown once)
    await waitFor(() =>
      expect(screen.getByText("xyz999-full-secret-token")).toBeInTheDocument(),
    );
  });

  it("after dismissing token modal, list shows new token_prefix", async () => {
    // MSW re-orders: after create, GET returns both curators
    server.use(
      http.get("*/api/admin/curators", () =>
        HttpResponse.json([
          ...CURATORS_INITIAL,
          { id: "c2", name: "Dr X", token_prefix: "xyz999", created_utc: "2026-04-30T10:00:00Z" },
        ]),
      ),
    );

    render(wrapped());
    await waitFor(() => expect(screen.getByText("Dr Müller")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    const nameInput = await screen.findByPlaceholderText(/name/i);
    fireEvent.change(nameInput, { target: { value: "Dr X" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() =>
      expect(screen.getByText("xyz999-full-secret-token")).toBeInTheDocument(),
    );

    // Dismiss dialog
    fireEvent.click(screen.getByRole("button", { name: /done/i }));

    // List re-renders with new prefix
    await waitFor(() => expect(screen.getByText("Dr X")).toBeInTheDocument());
    expect(screen.getByText("xyz999")).toBeInTheDocument();
  });
});

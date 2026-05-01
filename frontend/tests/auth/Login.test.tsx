import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Login } from "../../src/auth/routes/Login";

const server = setupServer(
  http.post("http://127.0.0.1:8001/api/auth/check", async ({ request }) => {
    const body = await request.json() as { token: string };
    if (body.token === "ADMIN-T") return HttpResponse.json({ role: "admin", name: "admin" });
    if (body.token === "CUR-T") return HttpResponse.json({ role: "curator", name: "Dr Q" });
    return new HttpResponse(JSON.stringify({ detail: "invalid" }), { status: 401 });
  }),
);
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderLogin(initial = "/login") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/admin/*" element={<div>admin landing</div>} />
        <Route path="/curate/*" element={<div>curator landing</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login role detection", () => {
  it("admin token → /admin/inbox", async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "ADMIN-T");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText("admin landing")).toBeInTheDocument());
  });

  it("curator token → /curate/", async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "CUR-T");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText("curator landing")).toBeInTheDocument());
  });

  it("invalid token shows error", async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "WRONG");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText(/abgelehnt/i)).toBeInTheDocument());
  });
});

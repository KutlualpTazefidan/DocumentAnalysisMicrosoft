import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Login } from "../../src/auth/routes/Login";

const server = setupServer(
  http.post("*/api/auth/check", async ({ request }) => {
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

// The legacy API-Token flow now lives behind ``?legacy=1`` and is the
// non-default tab; reveal it by visiting the flag URL and selecting the
// "API-Token (alt)" tab before typing into the token field.
async function showTokenTab() {
  await userEvent.click(screen.getByRole("button", { name: /API-Token \(alt\)/i }));
}

describe("Login role detection", () => {
  it("admin token → /admin/inbox", async () => {
    renderLogin("/login?legacy=1");
    await showTokenTab();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "ADMIN-T");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText("admin landing")).toBeInTheDocument());
  });

  it("curator token → /curate/", async () => {
    renderLogin("/login?legacy=1");
    await showTokenTab();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "CUR-T");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText("curator landing")).toBeInTheDocument());
  });

  it("invalid token shows error", async () => {
    renderLogin("/login?legacy=1");
    await showTokenTab();
    await userEvent.type(screen.getByLabelText(/API-Token/i), "WRONG");
    await userEvent.click(screen.getByRole("button", { name: /Einloggen/i }));
    await waitFor(() => expect(screen.getByText(/abgelehnt/i)).toBeInTheDocument());
  });
});

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Login } from "../../src/routes/login";

const server = setupServer();
beforeEach(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderLogin(initial = "/login") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/docs" element={<div>Docs page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login route", () => {
  it("accepts a valid token and navigates to /docs", async () => {
    server.use(
      http.get("http://localhost/api/health", () =>
        HttpResponse.json({ status: "ok", goldens_root: "outputs" }),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/token/i), "tok-good");
    await user.click(screen.getByRole("button", { name: /einloggen/i }));
    expect(await screen.findByText(/docs page/i)).toBeInTheDocument();
    expect(sessionStorage.getItem("goldens.api_token")).toBe("tok-good");
  });

  it("shows error banner on rejected token", async () => {
    server.use(
      http.get("http://localhost/api/health", () =>
        HttpResponse.json({ detail: "invalid" }, { status: 401 }),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/token/i), "tok-bad");
    await user.click(screen.getByRole("button", { name: /einloggen/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/abgelehnt|rejected/i);
  });
});

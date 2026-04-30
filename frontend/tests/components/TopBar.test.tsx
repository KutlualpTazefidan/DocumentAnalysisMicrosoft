import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { TopBar } from "../../src/components/TopBar";

describe("TopBar", () => {
  beforeEach(() => sessionStorage.setItem("goldens.api_token", "tok"));

  function renderBar(slug?: string) {
    return render(
      <MemoryRouter initialEntries={[slug ? `/docs/${slug}/elements` : "/docs"]}>
        <Routes>
          <Route path="/docs" element={<TopBar />} />
          <Route path="/docs/:slug/elements" element={<TopBar />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("shows brand and a logout button", () => {
    renderBar();
    expect(screen.getByText(/goldens/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /abmelden/i })).toBeInTheDocument();
  });

  it("shows the active slug breadcrumb when in a doc", () => {
    renderBar("smoke-test-tragkorb");
    expect(screen.getByText(/smoke-test-tragkorb/)).toBeInTheDocument();
  });

  it("logout clears token and navigates to /login", async () => {
    const user = userEvent.setup();
    renderBar();
    await user.click(screen.getByRole("button", { name: /abmelden/i }));
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
    expect(await screen.findByText(/login page/i)).toBeInTheDocument();
  });
});

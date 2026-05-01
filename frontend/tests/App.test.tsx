import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";

describe("App route shell", () => {
  it("renders Login at /login", () => {
    render(<MemoryRouter initialEntries={["/login"]}><App /></MemoryRouter>);
    expect(screen.getByText(/Anmeldung/i)).toBeInTheDocument();
  });

  it("renders 404 for unknown path", () => {
    render(<MemoryRouter initialEntries={["/no/such/path"]}><App /></MemoryRouter>);
    expect(screen.getByText(/Page not found/i)).toBeInTheDocument();
  });
});

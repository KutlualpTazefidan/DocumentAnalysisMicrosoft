import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TableElementView } from "../../src/components/TableElementView";
import type { DocumentElement } from "../../src/types/domain";

const tableElement: DocumentElement = {
  element_id: "p2-table",
  page_number: 2,
  element_type: "table",
  content: "M6 | 12 Nm | DIN 912\nM8 | 28 Nm | DIN 912\n...",
  table_dims: [4, 3],
  table_full_content:
    "Schraubentyp | Anzugsdrehmoment | Norm\nM6 | 12 Nm | DIN 912\nM8 | 28 Nm | DIN 912\nM10 | 55 Nm | DIN 912",
};

describe("TableElementView", () => {
  it("renders compact stub by default with toggle hint", () => {
    render(<TableElementView element={tableElement} />);
    expect(screen.getByText(/M6/)).toBeInTheDocument();
    expect(screen.getByText(/M8/)).toBeInTheDocument();
    expect(screen.queryByText(/M10/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /volle tabelle/i })).toBeInTheDocument();
  });

  it("toggles to full content when button clicked", async () => {
    const user = userEvent.setup();
    render(<TableElementView element={tableElement} />);
    await user.click(screen.getByRole("button", { name: /volle tabelle/i }));
    expect(screen.getByText(/M10/)).toBeInTheDocument();
    expect(screen.getByText(/55 Nm/)).toBeInTheDocument();
  });

  it("shows table dims badge", () => {
    render(<TableElementView element={tableElement} />);
    expect(screen.getByText(/4×3/)).toBeInTheDocument();
  });
});

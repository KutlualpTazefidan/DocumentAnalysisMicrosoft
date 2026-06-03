// frontend/src/admin/components/charts/__tests__/DiagnosticBar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiagnosticBar } from "../DiagnosticBar";

describe("DiagnosticBar", () => {
  it("renders the heading", () => {
    render(<DiagnosticBar data={{ split: 1, no_decomposition: 0, clean: 9, total: 10 }} />);
    expect(screen.getByText("Diagnose-Flags")).toBeInTheDocument();
  });
});

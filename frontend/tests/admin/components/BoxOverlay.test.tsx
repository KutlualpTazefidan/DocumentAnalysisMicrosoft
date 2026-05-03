// frontend/tests/local-pdf/components/BoxOverlay.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BoxOverlay } from "../../../src/admin/components/BoxOverlay";

const box = {
  box_id: "p1-b0",
  page: 1,
  bbox: [10, 20, 100, 200] as [number, number, number, number],
  kind: "paragraph" as const,
  confidence: 0.92,
  reading_order: 0,
  manually_activated: false,
};

describe("BoxOverlay", () => {
  it("renders kind label + confidence", () => {
    render(<BoxOverlay box={box} selected={false} onSelect={() => {}} onChange={() => {}} scale={1} />);
    expect(screen.getByText(/paragraph/)).toBeInTheDocument();
    expect(screen.getByText(/0\.92/)).toBeInTheDocument();
  });

  it("calls onSelect with boxId when clicked", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onChange={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    expect(onSelect).toHaveBeenCalledWith("p1-b0");
  });

  it("calls onSelect with boxId on shift-click (single-select)", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onChange={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"), { shiftKey: true });
    expect(onSelect).toHaveBeenCalledWith("p1-b0");
  });

  it("renders 4 corner handles when selected", () => {
    render(<BoxOverlay box={box} selected={true} onSelect={() => {}} onChange={() => {}} scale={1} />);
    expect(screen.getAllByTestId(/handle-/)).toHaveLength(4);
  });

  it("flashes yellow when confidence < 0.7", () => {
    const lowBox = { ...box, confidence: 0.5 };
    render(<BoxOverlay box={lowBox} selected={false} onSelect={() => {}} onChange={() => {}} scale={1} />);
    const el = screen.getByTestId("box-p1-b0");
    expect(el.className).toMatch(/low-confidence/);
  });
});

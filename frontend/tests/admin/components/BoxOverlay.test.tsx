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
    render(<BoxOverlay box={box} selected={false} onSelect={() => {}} onCommit={() => {}} scale={1} />);
    expect(screen.getByText(/paragraph/)).toBeInTheDocument();
    expect(screen.getByText(/0\.92/)).toBeInTheDocument();
  });

  it("calls onSelect with boxId when clicked", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onCommit={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    expect(onSelect).toHaveBeenCalledWith("p1-b0");
  });

  it("calls onSelect with boxId on shift-click (single-select)", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onCommit={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"), { shiftKey: true });
    expect(onSelect).toHaveBeenCalledWith("p1-b0");
  });

  it("renders 4 corner handles when selected", () => {
    render(<BoxOverlay box={box} selected={true} onSelect={() => {}} onCommit={() => {}} scale={1} />);
    expect(screen.getAllByTestId(/handle-/)).toHaveLength(4);
  });

  it("flashes yellow when confidence < 0.7", () => {
    const lowBox = { ...box, confidence: 0.5 };
    render(<BoxOverlay box={lowBox} selected={false} onSelect={() => {}} onCommit={() => {}} scale={1} />);
    const el = screen.getByTestId("box-p1-b0");
    expect(el.className).toMatch(/low-confidence/);
  });

  it("commits a resize exactly once on mouse-up — never per mouse-move", () => {
    const onCommit = vi.fn();
    render(<BoxOverlay box={box} selected={true} onSelect={() => {}} onCommit={onCommit} scale={1} />);
    fireEvent.mouseDown(screen.getByTestId("handle-br"), { clientX: 100, clientY: 200 });
    fireEvent.mouseMove(window, { clientX: 110, clientY: 210 });
    fireEvent.mouseMove(window, { clientX: 130, clientY: 240 });
    fireEvent.mouseMove(window, { clientX: 150, clientY: 260 });
    // Nothing persisted while dragging — this guards against per-pixel re-extract.
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.mouseUp(window);
    expect(onCommit).toHaveBeenCalledTimes(1);
    // br corner extended by (dx=50, dy=60) at scale 1 from orig [10,20,100,200]
    expect(onCommit).toHaveBeenCalledWith("p1-b0", [10, 20, 150, 260]);
  });

  it("shows no handles when readOnly (select-only on finished pages)", () => {
    render(<BoxOverlay box={box} selected={true} readOnly onSelect={() => {}} onCommit={() => {}} scale={1} />);
    expect(screen.queryAllByTestId(/handle-/)).toHaveLength(0);
  });
});

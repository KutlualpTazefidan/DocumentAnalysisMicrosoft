// frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts
import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useBoxHotkeys } from "../../../src/admin/hooks/useBoxHotkeys";

describe("useBoxHotkeys", () => {
  it("invokes setKind for h/p/t/f/c/q/l", () => {
    const setKind = vi.fn();
    const deactivate = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, deactivate, split, newBox, del }));
    for (const [key, kind] of [
      ["h", "heading"],
      ["p", "paragraph"],
      ["t", "table"],
      ["f", "figure"],
      ["c", "caption"],
      ["q", "formula"],
      ["l", "list_item"],
    ] as const) {
      fireEvent.keyDown(window, { key });
      expect(setKind).toHaveBeenLastCalledWith(kind);
    }
  });

  it("x maps to deactivate", () => {
    const setKind = vi.fn();
    const deactivate = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, deactivate, split, newBox, del }));
    fireEvent.keyDown(window, { key: "x" });
    expect(deactivate).toHaveBeenCalled();
    expect(setKind).not.toHaveBeenCalled();
  });

  it("n + Backspace map to newBox / delete; '/' is no longer a hotkey", () => {
    const setKind = vi.fn();
    const deactivate = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, deactivate, split, newBox, del }));
    fireEvent.keyDown(window, { key: "n" });
    expect(newBox).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "/" });
    expect(split).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Backspace" });
    expect(del).toHaveBeenCalled();
  });

  it("ignores keystrokes when enabled is false", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: false, setKind, deactivate: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    fireEvent.keyDown(window, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
  });

  it("ignores keystrokes when target is an input", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, deactivate: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
    input.remove();
  });
});

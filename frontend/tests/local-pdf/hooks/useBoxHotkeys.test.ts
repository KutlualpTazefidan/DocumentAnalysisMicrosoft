// frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts
import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useBoxHotkeys } from "../../../src/local-pdf/hooks/useBoxHotkeys";

describe("useBoxHotkeys", () => {
  it("invokes setKind for h/p/t/f/c/q/l/x", () => {
    const setKind = vi.fn();
    const merge = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge, split, newBox, del }));
    for (const [key, kind] of [
      ["h", "heading"],
      ["p", "paragraph"],
      ["t", "table"],
      ["f", "figure"],
      ["c", "caption"],
      ["q", "formula"],
      ["l", "list_item"],
      ["x", "discard"],
    ] as const) {
      fireEvent.keyDown(window, { key });
      expect(setKind).toHaveBeenLastCalledWith(kind);
    }
  });

  it("m/n//// + Backspace map to merge / newBox / split / delete", () => {
    const setKind = vi.fn();
    const merge = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge, split, newBox, del }));
    fireEvent.keyDown(window, { key: "m" });
    expect(merge).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "n" });
    expect(newBox).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "/" });
    expect(split).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Backspace" });
    expect(del).toHaveBeenCalled();
  });

  it("ignores keystrokes when enabled is false", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: false, setKind, merge: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    fireEvent.keyDown(window, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
  });

  it("ignores keystrokes when target is an input", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
    input.remove();
  });
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useKeyboardShortcuts } from "../../src/hooks/useKeyboardShortcuts";

describe("useKeyboardShortcuts", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("calls handler for matching key when focus is not in input", () => {
    const onJ = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: onJ }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "j" }));
    expect(onJ).toHaveBeenCalled();
  });

  it("does NOT call handler when focus is in textarea", () => {
    const onJ = vi.fn();
    document.body.innerHTML = '<textarea id="t"></textarea>';
    const ta = document.getElementById("t") as HTMLTextAreaElement;
    ta.focus();
    renderHook(() => useKeyboardShortcuts({ j: onJ }));
    ta.dispatchEvent(new KeyboardEvent("keydown", { key: "j", bubbles: true }));
    expect(onJ).not.toHaveBeenCalled();
  });

  it("calls ArrowDown handler", () => {
    const onArrow = vi.fn();
    renderHook(() => useKeyboardShortcuts({ ArrowDown: onArrow }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    expect(onArrow).toHaveBeenCalled();
  });
});

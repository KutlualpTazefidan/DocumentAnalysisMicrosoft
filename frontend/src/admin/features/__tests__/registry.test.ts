import { describe, expect, it } from "vitest";
import { WORKSPACE_TABS } from "../registry";

describe("workspace registry", () => {
  it("auto-discovers descriptors, sorted by order, Dateien first", () => {
    expect(WORKSPACE_TABS.length).toBeGreaterThanOrEqual(2);
    const orders = WORKSPACE_TABS.map((t) => t.order);
    expect([...orders]).toEqual([...orders].sort((a, b) => a - b));
    expect(WORKSPACE_TABS[0].key).toBe("files");
    for (const t of WORKSPACE_TABS) {
      expect(typeof t.key).toBe("string");
      expect(typeof t.label).toBe("string");
      expect(typeof t.requiresFile).toBe("boolean");
      expect(t.Component).toBeTruthy();
      expect(t.icon).toBeTruthy();
    }
    expect(WORKSPACE_TABS.find((t) => t.key === "statistics")?.requiresFile).toBe(true);
  });
});

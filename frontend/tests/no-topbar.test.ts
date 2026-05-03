import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

describe("TopBar removed", () => {
  it("file gone", () => {
    expect(existsSync(resolve(__dirname, "../src/components/TopBar.tsx"))).toBe(false);
  });
});

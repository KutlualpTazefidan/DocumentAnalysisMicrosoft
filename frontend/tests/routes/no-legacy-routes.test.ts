import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

describe("legacy routes removed", () => {
  it.each([
    "src/routes/docs-index.tsx",
    "src/routes/doc-elements.tsx",
    "src/routes/doc-synthesise.tsx",
  ])("%s does not exist", (rel) => {
    expect(existsSync(resolve(__dirname, "../../", rel))).toBe(false);
  });
});

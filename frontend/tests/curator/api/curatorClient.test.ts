import { describe, it, expect } from "vitest";
describe("curatorClient module", () => {
  it("exports apiFetch", async () => {
    const m = await import("../../../src/curator/api/curatorClient");
    expect(typeof m.apiFetch).toBe("function");
  });
});

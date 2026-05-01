import { describe, it, expect } from "vitest";

describe("adminClient module shape", () => {
  it("re-exports from new location", async () => {
    const mod = await import("../../../src/admin/api/adminClient");
    expect(typeof mod.apiFetch).toBe("function");
    expect(typeof mod.apiBase).toBe("function");
    expect(typeof mod.authHeaders).toBe("function");
  });

  it("apiBase includes /api/admin in default", async () => {
    const { apiBase } = await import("../../../src/admin/api/adminClient");
    expect(apiBase().endsWith("/api/admin")).toBe(true);
  });
});

import { describe, it, expect } from "vitest";

describe("adminClient module shape", () => {
  it("re-exports from new location", async () => {
    const mod = await import("../../../src/admin/api/adminClient");
    expect(typeof mod.apiFetch).toBe("function");
    expect(typeof mod.apiBase).toBe("function");
    expect(typeof mod.authHeaders).toBe("function");
  });

  it("apiBase returns the BASE prefix only (call sites add /api/admin/...)", async () => {
    const { apiBase } = await import("../../../src/admin/api/adminClient");
    // Default BASE is "" so apiBase() === "". Direct-fetch call sites
    // (PdfPage, useExtract streamSegment/streamExtract) include the
    // full "/api/admin/docs/..." path themselves.
    expect(apiBase()).toBe("");
  });
});

// frontend/tests/local-pdf/api/docs.test.ts
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { listDocs, uploadDoc, getDoc, getSegments, updateBox } from "../../../src/local-pdf/api/docs";

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs", () =>
    HttpResponse.json([
      { slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 },
    ]),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep", () =>
    HttpResponse.json({ slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 }),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({ slug: "rep", boxes: [{ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.9, reading_order: 0 }] }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "paragraph", confidence: 0.9, reading_order: 0 }),
  ),
  http.post("http://127.0.0.1:8001/api/docs", () =>
    HttpResponse.json({ slug: "new", filename: "New.pdf", pages: 1, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 }, { status: 201 }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("local-pdf docs api", () => {
  it("listDocs returns inbox", async () => {
    const out = await listDocs("tok");
    expect(out).toHaveLength(1);
    expect(out[0].slug).toBe("rep");
  });

  it("getDoc returns metadata", async () => {
    const m = await getDoc("rep", "tok");
    expect(m.pages).toBe(4);
  });

  it("getSegments returns boxes", async () => {
    const s = await getSegments("rep", "tok");
    expect(s.boxes[0].kind).toBe("heading");
  });

  it("updateBox sends PUT", async () => {
    const out = await updateBox("rep", "p1-b0", { kind: "paragraph" }, "tok");
    expect(out.kind).toBe("paragraph");
  });

  it("uploadDoc sends multipart", async () => {
    const blob = new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])], { type: "application/pdf" });
    const file = new File([blob], "New.pdf", { type: "application/pdf" });
    const out = await uploadDoc(file, "tok");
    expect(out.slug).toBe("new");
  });
});

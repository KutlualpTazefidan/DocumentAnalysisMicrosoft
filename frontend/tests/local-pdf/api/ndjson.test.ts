import { describe, expect, it } from "vitest";

import { readNdjsonLines } from "../../../src/local-pdf/api/ndjson";

function bodyFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
}

describe("readNdjsonLines", () => {
  it("splits on newline and parses JSON per line", async () => {
    const stream = bodyFrom(['{"type":"start","total_boxes":2}\n', '{"type":"element","box_id":"b1","html_snippet":"<p/>"}\n', '{"type":"complete","boxes_extracted":1}\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toHaveLength(3);
    expect(out[0].type).toBe("start");
    expect(out[2].boxes_extracted).toBe(1);
  });

  it("buffers partial lines across chunks", async () => {
    const stream = bodyFrom(['{"type":"start",', '"total_boxes":7}\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toEqual([{ type: "start", total_boxes: 7 }]);
  });

  it("ignores trailing empty line", async () => {
    const stream = bodyFrom(['{"type":"start","total_boxes":1}\n\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toHaveLength(1);
  });
});

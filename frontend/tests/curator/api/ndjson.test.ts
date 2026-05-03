import { describe, it, expect } from "vitest";
import { streamNdjson } from "../../../src/curator/api/ndjson";
import type { SynthLine } from "../../../src/shared/types/domain";

function makeResponseFromChunks(chunks: string[]): Response {
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
  return new Response(stream);
}

describe("streamNdjson", () => {
  it("yields one parsed object per newline-delimited JSON line", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","total_elements":2}\n',
      '{"type":"element","element_id":"p1-aaa","kept":3,"skipped_reason":null,"tokens_estimated":42}\n',
      '{"type":"complete","events_written":3,"prompt_tokens_estimated":42}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatchObject({ type: "start", total_elements: 2 });
    expect(lines[2]).toMatchObject({ type: "complete", events_written: 3 });
  });

  it("buffers a partial line across chunks", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","tota',
      'l_elements":5}\n{"type":"complete","events_written":0,"prompt_tokens_estimated":0}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ type: "start", total_elements: 5 });
  });

  it("ignores blank lines and trailing whitespace", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","total_elements":1}\n\n  \n{"type":"complete","events_written":0,"prompt_tokens_estimated":0}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(2);
  });
});

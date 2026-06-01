// Minimal walkthrough-recorder: drives a Playwright page through a sequence
// of steps and writes the same data.json+screenshots format as the legacy
// recorder (see existing tests/walkthrough/output/*/data.json files). Used
// by the per-flow record scripts in tests/walkthrough/record/.
//
// Example:
//   import { Recorder } from "./record-walkthrough.mjs";
//   const rec = new Recorder("extract-export", "http://127.0.0.1:5173");
//   const page = ...;
//   await rec.step(page, "Open extract page", {
//     actions: ["goto /admin/doc/.../extract"],
//     notes:   ["Topbar shows the Export button on the far right."],
//     shots:   [{ annotations: [{ kind: "highlight", selector: 'button:has-text("Export")', text: "Export button" }] }],
//   });
//   await rec.finish();

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const HERE = path.dirname(__filename);

function pad(n, w = 2) {
  return String(n).padStart(w, "0");
}

function stampDirSuffix(iso) {
  // 2026-05-31T11:42:03.527Z → 2026-05-31_11-42-03-527
  return iso.replace(/[:.]/g, "-").replace("T", "_").replace("Z", "");
}

export class Recorder {
  constructor(flowName, baseUrl) {
    this.flowName = flowName;
    this.baseUrl = baseUrl;
    this.startedAt = new Date().toISOString();
    this.steps = [];
    const safeName = flowName.replace(/[/\\]/g, "_");
    this.outDir = path.join(HERE, "output", `${safeName}_${stampDirSuffix(this.startedAt)}`);
    fs.mkdirSync(path.join(this.outDir, "screenshots"), { recursive: true });
  }

  /** Record one step. shots: array of { annotations, locator? } — each emits a screenshot. */
  async step(page, title, { actions = [], notes = [], shots = [{}] } = {}) {
    const stepIdx = this.steps.length;
    const startedAtMs = Date.now();
    const screenshots = [];

    for (let s = 0; s < shots.length; s++) {
      const cfg = shots[s] ?? {};
      const filename = `screenshots/${pad(stepIdx + 1)}_${pad(s + 1)}.png`;
      await page.screenshot({ path: path.join(this.outDir, filename), fullPage: false });

      const annotations = [];
      for (const ann of cfg.annotations ?? []) {
        const out = { kind: ann.kind, text: ann.text };
        if (ann.kind === "highlight") {
          out.selector = ann.selector;
          if (ann.selector) {
            try {
              const bb = await page.locator(ann.selector).first().boundingBox({ timeout: 1500 });
              if (bb) {
                out.box = {
                  x: Math.round(bb.x),
                  y: Math.round(bb.y),
                  width: Math.round(bb.width),
                  height: Math.round(bb.height),
                };
              }
            } catch {
              /* selector didn't match — leave out box; the loader handles missing box */
            }
          }
        }
        annotations.push(out);
      }

      const vp = page.viewportSize() ?? { width: 1400, height: 900 };
      screenshots.push({ filename, width: vp.width, height: vp.height, annotations });
    }

    const endedAtMs = Date.now();
    this.steps.push({
      index: stepIdx,
      title,
      startedAtMs,
      endedAtMs,
      actions,
      screenshots,
      notes,
      status: "ok",
    });
  }

  async finish() {
    const data = {
      name: this.flowName,
      startedAt: this.startedAt,
      endedAt: new Date().toISOString(),
      baseUrl: this.baseUrl,
      steps: this.steps,
    };
    fs.writeFileSync(path.join(this.outDir, "data.json"), JSON.stringify(data, null, 2));
    return this.outDir;
  }
}

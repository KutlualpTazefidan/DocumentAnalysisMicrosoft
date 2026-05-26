/**
 * Render a walkthrough as a Figma-style storyboard.
 *
 * Input:  ``<output_dir>/data.json`` + ``screenshots/`` (produced by
 *         ``walkthrough.ts``).
 * Output: ``<output_dir>/report.html`` (interactive in a browser) and
 *         ``<output_dir>/report.png`` (single full-page screenshot of
 *         the HTML — VSCode-friendly).
 */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";
import type {
  Annotation,
  ScreenshotEntry,
  StepData,
  WalkthroughData,
} from "./walkthrough";

export async function composeReport(outputDir: string): Promise<{
  htmlPath: string;
  pngPath: string;
}> {
  const dataPath = path.join(outputDir, "data.json");
  if (!fs.existsSync(dataPath)) {
    throw new Error(`data.json not found in ${outputDir}`);
  }
  const data: WalkthroughData = JSON.parse(fs.readFileSync(dataPath, "utf8"));

  const html = renderHtml(data, outputDir);
  const htmlPath = path.join(outputDir, "report.html");
  fs.writeFileSync(htmlPath, html);

  const pngPath = path.join(outputDir, "report.png");
  await renderHtmlToPng(htmlPath, pngPath);

  return { htmlPath, pngPath };
}

// ---- HTML renderer ----

function renderHtml(data: WalkthroughData, outputDir: string): string {
  const stepsHtml = data.steps.map((s) => renderStep(s, data, outputDir)).join("\n");
  const summary = renderSummary(data);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Walkthrough: ${escapeHtml(data.name)}</title>
  <style>${CSS}</style>
</head>
<body>
  <header class="page-header">
    <h1>${escapeHtml(data.name)}</h1>
    <div class="meta">
      <span>baseUrl: <code>${escapeHtml(data.baseUrl)}</code></span>
      <span>started: <code>${escapeHtml(data.startedAt)}</code></span>
      <span>steps: <strong>${data.steps.length}</strong></span>
      <span>console: <strong>${data.console.length}</strong></span>
      <span>network 4xx/5xx: <strong>${data.networkErrors.length}</strong></span>
      <span>JS errors: <strong>${data.pageErrors.length}</strong></span>
    </div>
  </header>
  ${summary}
  <main class="steps">
    ${stepsHtml}
  </main>
</body>
</html>`;
}

function renderSummary(data: WalkthroughData): string {
  const failed = data.steps.filter((s) => s.status === "failed");
  if (failed.length === 0 && data.pageErrors.length === 0 && data.networkErrors.length === 0) {
    return `<section class="summary summary--ok">All ${data.steps.length} steps passed — no console errors, no network 4xx/5xx, no JS errors.</section>`;
  }
  const parts: string[] = [];
  if (failed.length) parts.push(`<strong>${failed.length}</strong> failed step(s)`);
  if (data.pageErrors.length) parts.push(`<strong>${data.pageErrors.length}</strong> JS error(s)`);
  if (data.networkErrors.length) parts.push(`<strong>${data.networkErrors.length}</strong> network 4xx/5xx`);
  return `<section class="summary summary--issues">⚠ ${parts.join(" · ")}</section>`;
}

function renderStep(s: StepData, data: WalkthroughData, outputDir: string): string {
  const screenshots = s.screenshots
    .map((shot) => renderShot(shot, outputDir))
    .join("\n");
  const consoleHere = data.console.filter((c) => c.stepIndex === s.index);
  const networkHere = data.networkErrors.filter((n) => n.stepIndex === s.index);
  const errsHere = data.pageErrors.filter((e) => e.stepIndex === s.index);
  const statusClass = s.status === "failed" ? "step--failed" : "step--ok";
  const headerStatus =
    s.status === "failed"
      ? `<span class="badge badge--err">FAILED</span>`
      : `<span class="badge badge--ok">OK</span>`;
  return `<section class="step ${statusClass}">
    <header class="step-header">
      <span class="step-index">${String(s.index + 1).padStart(2, "0")}</span>
      <h2>${escapeHtml(s.title)}</h2>
      ${headerStatus}
      <span class="step-duration">${s.endedAtMs - s.startedAtMs} ms</span>
    </header>
    <div class="step-body">
      <div class="step-shots">${screenshots}</div>
      <aside class="step-side">
        ${renderActions(s.actions)}
        ${renderConsole(consoleHere)}
        ${renderNetwork(networkHere)}
        ${renderJsErrors(errsHere)}
        ${s.errorMessage ? `<div class="step-error">${escapeHtml(s.errorMessage)}</div>` : ""}
      </aside>
    </div>
  </section>`;
}

function renderShot(shot: ScreenshotEntry, outputDir: string): string {
  // Embed screenshot as a relative <img>. Annotations land as
  // absolute-positioned SVG overlays scaled to the image's natural
  // size — the browser handles responsive scaling via CSS.
  const overlays = renderOverlays(shot.annotations, shot.width, shot.height);
  const fileBaseUrl = path.relative(outputDir, path.join(outputDir, shot.filename));
  return `<figure class="shot">
    <div class="shot-frame">
      <img src="${fileBaseUrl}" alt="" />
      <svg class="shot-overlay" viewBox="0 0 ${shot.width} ${shot.height}" preserveAspectRatio="none">${overlays}</svg>
    </div>
    ${shot.note ? `<figcaption>${escapeHtml(shot.note)}</figcaption>` : ""}
  </figure>`;
}

function renderOverlays(anns: Annotation[], _w: number, _h: number): string {
  return anns
    .map((a) => {
      if (a.kind === "highlight" && a.box) {
        const { x, y, width, height } = a.box;
        const label = a.text
          ? `<text x="${x + 6}" y="${y - 6}" class="ov-label">${escapeHtml(a.text)}</text>`
          : "";
        return `<rect x="${x}" y="${y}" width="${width}" height="${height}" class="ov-highlight" />${label}`;
      }
      if (a.kind === "arrow" && a.boxFrom && a.boxTo) {
        const x1 = a.boxFrom.x + a.boxFrom.width / 2;
        const y1 = a.boxFrom.y + a.boxFrom.height / 2;
        const x2 = a.boxTo.x + a.boxTo.width / 2;
        const y2 = a.boxTo.y + a.boxTo.height / 2;
        const label = a.text
          ? `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 8}" class="ov-label">${escapeHtml(a.text)}</text>`
          : "";
        return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="ov-arrow" marker-end="url(#arrowhead)" />${label}`;
      }
      return "";
    })
    .concat([
      `<defs><marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#ec4899" /></marker></defs>`,
    ])
    .join("\n");
}

function renderActions(actions: string[]): string {
  if (!actions.length) return "";
  const items = actions.map((a) => `<li><code>${escapeHtml(a)}</code></li>`).join("");
  return `<div class="side-block">
    <h3>Actions</h3><ol>${items}</ol>
  </div>`;
}

function renderConsole(entries: { type: string; text: string }[]): string {
  if (!entries.length) return "";
  const lines = entries
    .map(
      (c) =>
        `<li class="c-${escapeHtml(c.type)}"><span class="c-type">${escapeHtml(c.type)}</span> ${escapeHtml(c.text)}</li>`,
    )
    .join("");
  return `<div class="side-block">
    <h3>Console (${entries.length})</h3><ul class="console-list">${lines}</ul>
  </div>`;
}

function renderNetwork(entries: { url: string; method: string; status: number }[]): string {
  if (!entries.length) return "";
  const lines = entries
    .map(
      (n) =>
        `<li>${n.method} <strong>${n.status}</strong> <code>${escapeHtml(n.url)}</code></li>`,
    )
    .join("");
  return `<div class="side-block side-block--net">
    <h3>Network 4xx/5xx (${entries.length})</h3><ul>${lines}</ul>
  </div>`;
}

function renderJsErrors(entries: { name: string; message: string }[]): string {
  if (!entries.length) return "";
  const lines = entries
    .map((e) => `<li><strong>${escapeHtml(e.name)}</strong>: ${escapeHtml(e.message)}</li>`)
    .join("");
  return `<div class="side-block side-block--err">
    <h3>JS errors (${entries.length})</h3><ul>${lines}</ul>
  </div>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---- HTML → PNG via headless Playwright ----

async function renderHtmlToPng(htmlPath: string, pngPath: string): Promise<void> {
  // Use a fresh headless chromium just for the snapshot — keeps the
  // PNG render independent of whatever browser context the
  // walkthrough itself used.
  const browser = await chromium.launch({ headless: true });
  try {
    const ctx = await browser.newContext({
      viewport: { width: 1400, height: 900 },
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    await page.goto(`file://${path.resolve(htmlPath)}`);
    // Wait for images to load so the screenshot doesn't capture
    // empty frames.
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: pngPath, fullPage: true });
  } finally {
    await browser.close();
  }
}

// ---- Styles (inlined into the HTML) ----

const CSS = `
  :root {
    --c-bg: #f8fafc;
    --c-card: #ffffff;
    --c-border: #e2e8f0;
    --c-text: #0f172a;
    --c-muted: #64748b;
    --c-accent: #2563eb;
    --c-ok: #16a34a;
    --c-warn: #f59e0b;
    --c-err: #dc2626;
    --c-pink: #ec4899;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    background: var(--c-bg);
    color: var(--c-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  code, pre {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 0.85em;
    background: #f1f5f9;
    padding: 1px 4px;
    border-radius: 3px;
  }
  .page-header {
    background: var(--c-card);
    border-bottom: 1px solid var(--c-border);
    padding: 24px 32px;
  }
  .page-header h1 {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
  }
  .page-header .meta {
    display: flex; gap: 16px;
    margin-top: 8px;
    font-size: 12px;
    color: var(--c-muted);
    flex-wrap: wrap;
  }
  .summary {
    margin: 24px 32px;
    padding: 12px 16px;
    border-radius: 6px;
    font-weight: 500;
  }
  .summary--ok { background: #dcfce7; color: #166534; }
  .summary--issues { background: #fef3c7; color: #92400e; }
  .steps { padding: 0 32px 48px; }
  .step {
    background: var(--c-card);
    border: 1px solid var(--c-border);
    border-radius: 8px;
    margin-bottom: 24px;
    overflow: hidden;
  }
  .step--failed { border-color: var(--c-err); box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.08); }
  .step-header {
    display: flex; align-items: center; gap: 12px;
    padding: 16px 24px;
    border-bottom: 1px solid var(--c-border);
    background: #f8fafc;
  }
  .step-header h2 { margin: 0; font-size: 16px; font-weight: 600; flex: 1; }
  .step-index {
    display: inline-block;
    background: var(--c-accent); color: #fff;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
    font-family: monospace;
  }
  .step-duration { color: var(--c-muted); font-size: 12px; }
  .badge {
    padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  }
  .badge--ok { background: #dcfce7; color: #166534; }
  .badge--err { background: #fee2e2; color: #991b1b; }
  .step-body { display: grid; grid-template-columns: 2fr 1fr; gap: 0; }
  .step-shots { padding: 20px; border-right: 1px solid var(--c-border); display: flex; flex-direction: column; gap: 16px; }
  .shot {
    margin: 0;
    border: 1px solid var(--c-border);
    border-radius: 6px;
    overflow: hidden;
    background: #fff;
  }
  .shot-frame {
    position: relative;
    line-height: 0;
  }
  .shot-frame img { max-width: 100%; height: auto; display: block; }
  .shot-overlay {
    position: absolute; top: 0; left: 0;
    width: 100%; height: 100%;
    pointer-events: none;
  }
  .ov-highlight { fill: rgba(6, 182, 212, 0.18); stroke: #06b6d4; stroke-width: 3; }
  .ov-arrow { stroke: var(--c-pink); stroke-width: 3; fill: none; }
  .ov-label { font-family: monospace; font-size: 14px; fill: #0e7490; font-weight: 600; }
  .shot figcaption {
    padding: 8px 12px;
    font-size: 13px;
    color: var(--c-muted);
    background: #f8fafc;
    border-top: 1px solid var(--c-border);
  }
  .step-side {
    padding: 20px;
    background: #fcfcfd;
    display: flex; flex-direction: column; gap: 16px;
    font-size: 12px;
  }
  .side-block h3 {
    margin: 0 0 6px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--c-muted);
  }
  .side-block ol, .side-block ul { margin: 0; padding-left: 18px; }
  .side-block li { margin-bottom: 2px; word-break: break-word; }
  .side-block--net h3 { color: var(--c-warn); }
  .side-block--err h3 { color: var(--c-err); }
  .console-list .c-error { color: var(--c-err); }
  .console-list .c-warn { color: var(--c-warn); }
  .c-type {
    display: inline-block;
    padding: 0 4px;
    margin-right: 4px;
    border-radius: 3px;
    background: #e2e8f0;
    font-family: monospace;
    font-size: 10px;
    text-transform: uppercase;
  }
  .step-error {
    background: #fee2e2;
    border-left: 3px solid var(--c-err);
    padding: 8px 12px;
    color: #991b1b;
    border-radius: 4px;
    font-size: 12px;
  }
`;

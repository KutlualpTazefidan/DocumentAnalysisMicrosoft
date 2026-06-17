// Walkthrough recording: extract-text-edit
// Tour the in-place HTML-editor: each element lives inside the editor's
// Shadow-DOM as a [data-source-box]; first click selects (+ highlights
// the corresponding PDF box), second click within ~500ms enters
// contentEditable mode, blur triggers PATCH /elements/{box_id} which
// persists the change to mineru-out.json + html.html.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";
const MARKER = "[BEARBEITUNGSMARKE]";

async function getHtmlSnapshot() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/html`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? (await r.json()).html ?? "" : "";
}
async function restoreHtml(html) {
  await fetch(`${API}/api/admin/docs/${SLUG}/html`, {
    method: "PUT",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

const originalHtml = await getHtmlSnapshot();
const rec = new Recorder("extract-text-edit", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Resolve a target box. Playwright locators auto-pierce open shadow roots,
// so `[data-source-box]` finds the editor children even though they live
// inside a shadow root. Pick the first paragraph on the current page.
const targetLocator = page.locator('[data-source-box]').first();
const targetBoxId = await targetLocator.getAttribute("data-source-box");
console.log("Target box:", targetBoxId);

// Step 1: editor visible, target element highlighted
await rec.step(page, "HTML-Editor: pro MinerU-Element ein editierbares Shadow-DOM-Element", {
  actions: [`goto /admin/doc/${SLUG}/extract`, `locate first [data-source-box] → ${targetBoxId}`],
  notes: [
    "Der HTML-Editor lebt komplett im Shadow-DOM — schützt die App vor CSS-Konflikten mit dem extrahierten Inhalt.",
    "Jedes MinerU-Element trägt data-source-box=<box_id> und ist eigenständig anklickbar.",
    "Doppelklick-Schema: erster Klick selektiert (das Pendant im PDF-Render blinkt auf), zweiter Klick innerhalb ~800 ms macht das Element contentEditable.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-source-box="${targetBoxId}"]`, text: "Ziel-Element für die Bearbeitung" },
  ] }],
});

// Step 2: enter edit mode (double-click), type a marker, blur to save
await targetLocator.click();
await page.waitForTimeout(120);
await targetLocator.click();          // second click within window → contentEditable
await page.waitForTimeout(250);
await page.keyboard.type(" " + MARKER, { delay: 25 });
await page.waitForTimeout(400);
// Blur: click into the sidebar (definitely outside the editor)
await page.locator("aside").first().click({ position: { x: 20, y: 20 } });
// Poll until savingStatus reaches a stable "Gespeichert" state (or fail-state).
// react-query re-renders html + mineru on success → can take ~1-2s end-to-end.
await page
  .waitForFunction(() => /Gespeichert/i.test(document.body.innerText), { timeout: 6000 })
  .catch(() => {});
await page.waitForTimeout(400);
await rec.step(page, `Doppelklick → contentEditable → „${MARKER}“ tippen → Blur speichert`, {
  actions: [
    `click [data-source-box="${targetBoxId}"]  (×2 within ~500ms)`,
    `type " ${MARKER}"`,
    "blur to trigger PATCH /elements/{box_id}",
  ],
  notes: [
    "Der Editor merkt sich beim Einstieg den OuterHTML-Snapshot als Original. Beim Blur wird der neue OuterHTML mit dem Original verglichen — nur bei Unterschied wird PATCH abgesetzt.",
    "Speicher-Endpoint: PATCH /api/admin/docs/{slug}/elements/{box_id} mit body {html_snippet}.",
    "Server re-rendert LaTeX in der neuen HTML, schreibt mineru-out.json + html.html und invalidiert die react-query-Caches für html + mineru.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-source-box="${targetBoxId}"]`, text: `Marker „${MARKER}“ am Ende sichtbar` },
  ] }],
});

// Step 3: reload, verify marker persisted in the live editor
await page.reload();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
const markerVisible = await page.locator(`text=${MARKER}`).count();
const persisted = markerVisible > 0;
await rec.step(page, persisted ? "Reload bestätigt: Marker im Server-HTML" : "Marker im Reload nicht gefunden", {
  actions: [`page.reload()`, `count "text=${MARKER}" via locator`],
  notes: [
    persisted
      ? "Nach Reload findet sich der Marker wieder im Editor — PATCH lief sauber durch, html.html + mineru-out.json sind aktualisiert."
      : "Marker nach Reload nicht sichtbar — möglicherweise hat Playwright den Blur nicht ausgelöst (z.B. Click in den Editor-Body statt außerhalb).",
    `Locator-Hits für „${MARKER}“: ${markerVisible}`,
    "Geänderter Text landet im sourceelements.json beim nächsten Export-Klick (POST /export liest html.html als Quelle).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-source-box="${targetBoxId}"]`, text: persisted ? "Marker persistiert ✓" : "Marker fehlt ✗" },
  ] }],
});

// Cleanup: restore original HTML so downstream recordings see the pristine doc.
if (originalHtml) {
  await restoreHtml(originalHtml);
  console.log("Original HTML restored.");
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

// Walkthrough recording: extract-page-extract
// Tour the per-page and full-document re-extraction triggers:
//   "Diese Seite extrahieren" (right sidebar) — runs MinerU only on the
//                                                currently-viewed page
//   "Alle Seiten extrahieren" (top sub-bar)  — runs the full pipeline
//                                                across every page

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("extract-page-extract", BASE);

// Step 1: Extrahieren-Seite mit Boxen
await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(1500);
await rec.step(page, "Extrahieren-Seite: zwei Eintrittspunkte für Re-Extraktion", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "„Alle Seiten extrahieren“ (oben, BAM-cyan) startet den Voll-Lauf über alle Seiten — gut für initiale Extraktion oder nach Schema-Updates.",
    "„Diese Seite extrahieren“ (rechts) wirkt nur auf die aktuell sichtbare Seite — schnell für Korrektur einzelner Seiten ohne den ganzen PDF neu zu jagen.",
    "Beide rufen denselben /segment-Endpoint, nur mit unterschiedlichem ?start=&end=-Range.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: 'button[aria-label="Re-extract all"]', text: "Voll-Lauf — alle Seiten" },
      { kind: "highlight", selector: 'button[aria-label="Re-extract this page"]', text: "Nur die aktuelle Seite" },
    ],
  }],
});

// Step 2: Click "Diese Seite extrahieren"
const thisPage = page.locator('button[aria-label="Re-extract this page"]');
await thisPage.click();
await page.waitForTimeout(600);
await rec.step(page, "„Diese Seite extrahieren“ → Lauf startet", {
  actions: ["click button[aria-label='Re-extract this page']"],
  notes: [
    "Beim Klick öffnet sich ein NDJSON-Stream vom Backend; UI streamt Worker-Events in Real-Time.",
    "Während der Lauf läuft, ist das HTML-Editor-Panel mit „loading…“ überlagert; Boxen blinken nicht (vorhandene Geometrie bleibt sichtbar).",
    "Typische Laufzeit für eine Seite: ~30-60s (DocLayout-YOLO + MinerU VLM pro Seite).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Stream-Events landen im Worker-Status-Indicator (unten links)" },
  ] }],
});

// Wait for finish — backend status returns extracted when done
let tries = 0;
while (tries++ < 40) {
  const r = await fetch(`http://127.0.0.1:8001/api/admin/docs/${SLUG}`, {
    headers: { "X-Auth-Token": TOKEN },
  });
  const j = await r.json();
  if (j.status === "extracted") break;
  await page.waitForTimeout(3000);
}

await page.waitForTimeout(1500);
await rec.step(page, "Lauf abgeschlossen — Seite frisch extrahiert", {
  actions: ["poll backend status until extracted"],
  notes: [
    "Status springt zurück auf „Extrahiert“ (DocStatus.extracted) sobald write_segments + write_mineru + write_html durch sind.",
    "Box-Overlay aktualisiert sich automatisch (react-query invalidiert segments/html/mineru nach dem Stream).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid^="box-"]', text: "Frische Box-Geometrie aus dem Re-Lauf" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

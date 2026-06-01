// Walkthrough recording: extract-export
// Tour the Export action: open the Extrahieren tab on an extracted document,
// highlight the Export button, click it, observe the success toast, verify
// the produced sourceelements.json on disk.
//
// Usage:
//   node tests/walkthrough/record/extract-export.mjs [<slug>]
// Default slug is the Kohavi test doc uploaded earlier.

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

// Prime auth (HashRouter, sessionStorage-backed)
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("extract-export", BASE);

// ── Step 1: land on Extrahieren ────────────────────────────────────────────
await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1500); // let mineru-image + html load
await rec.step(page, "Extrahieren-Seite mit extrahiertem Dokument öffnen", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "Voraussetzung: Dokument wurde bereits segmentiert/extrahiert (Boxen + Text vorhanden, Status „Extrahiert“).",
    "Die Sub-Topbar zeigt rechts vier Doc-Level-Aktionen: Verzeichnisse erkennen, Alle Seiten extrahieren, Abgeschlossene Seiten schützen, Export.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: 'button[aria-label="Export sourceelements.json"]', text: "Export-Button — schreibt sourceelements.json in den Daten-Ordner des Dokuments" },
    ],
  }],
});

// ── Step 2: Export-Button drücken ──────────────────────────────────────────
const exportBtn = page.locator('button[aria-label="Export sourceelements.json"]');
await exportBtn.click();
// Wait for toast to appear
await page.waitForSelector('text=Exported sourceelements.json', { timeout: 5000 }).catch(() => {});
await page.waitForTimeout(300);
await rec.step(page, "Export anstoßen → Toast „Exported sourceelements.json“", {
  actions: ["click Export-button", "wait for success toast"],
  notes: [
    "Klick auf Export ruft POST /api/admin/docs/{slug}/export auf — der Server schreibt synchron sourceelements.json.",
    "Erfolgsmeldung als Toast unten rechts; kein Browser-Download (Datei landet auf dem Server, nicht beim Nutzer).",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: 'text=Exported sourceelements.json', text: "Success-Toast bestätigt Server-Schreibvorgang" },
    ],
  }],
});

// ── Step 3: Verify the file on disk (no UI, but the artifact IS the deliverable)
const dataRoot = "/home/ktazefid/Documents/local-pdf-test/data";
const jsonPath = `${dataRoot}/${SLUG}/sourceelements.json`;
const exists = fs.existsSync(jsonPath);
const size = exists ? fs.statSync(jsonPath).size : 0;
const peek = exists ? JSON.parse(fs.readFileSync(jsonPath, "utf8")) : null;
const elementCount = peek?.elements?.length ?? peek?.source_elements?.length ?? Object.keys(peek ?? {}).length;
await rec.step(page, "Ergebnis prüfen — sourceelements.json liegt im Daten-Ordner", {
  actions: [`read ${jsonPath}`],
  notes: [
    exists ? `Datei vorhanden (${(size/1024).toFixed(1)} KB) mit ${elementCount} Source-Elementen.` : `❌ Datei fehlt unter ${jsonPath}.`,
    "Pfad: <data_root>/<slug>/sourceelements.json — wird vom Synthese-Schritt als Eingabe gelesen.",
  ],
  shots: [{
    annotations: [
      { kind: "note", text: `Datei-Pfad: ${jsonPath}` },
      { kind: "note", text: exists ? `Größe ${(size/1024).toFixed(1)} KB · ${elementCount} Elemente` : "Datei fehlt — Export schlug fehl" },
    ],
  }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

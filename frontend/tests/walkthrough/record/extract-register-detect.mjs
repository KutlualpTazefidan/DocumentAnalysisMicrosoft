// Walkthrough recording: extract-register-detect
// Tour the „Verzeichnisse erkennen“ feature: scan the document for TOC /
// list-of-figures / list-of-tables clusters and surface them in a panel
// so the curator can jump to register pages quickly.

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
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

const rec = new Recorder("extract-register-detect", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(1500);

// Step 1: Topbar mit Verzeichnisse-Button
await rec.step(page, "Extrahieren-Topbar: „Verzeichnisse erkennen“", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "„Verzeichnisse erkennen“ startet einen Doc-weiten Scan nach TOC-, Tabellen-, Abbildungs-Verzeichnis-Clustern.",
    "Ergebnis: einzelne Boxen werden zu Registern gruppiert + ein Panel zur schnellen Navigation listet sie auf.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[aria-label="Verzeichnisse erkennen und anzeigen"]', text: "Trigger für die Verzeichnis-Erkennung" },
  ] }],
});

// Step 2: click & observe loading
const btn = page.locator('button[aria-label="Verzeichnisse erkennen und anzeigen"]');
await btn.click();
await page.waitForTimeout(1500);
await rec.step(page, "Detect-Lauf läuft — POST /segments/detect-registers", {
  actions: ['click button "Verzeichnisse erkennen"'],
  notes: [
    "Backend ruft den Register-Detector (Heuristik über Box-Layout + Caption-Patterns).",
    "Antwort enthält Cluster mit Box-IDs + erkanntem Typ (toc / list_of_tables / list_of_figures / bibliography).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Spinner / Toast während des Laufs" },
  ] }],
});

// Wait for register panel to appear
await page.waitForTimeout(3000);

// Step 3: panel visible
await rec.step(page, "Register-Panel sichtbar — Cluster + Navigation", {
  actions: ["wait for register panel"],
  notes: [
    "Pro erkanntes Verzeichnis ein Eintrag mit Typ-Badge + Box-Anzahl.",
    "Klick auf einen Eintrag → Sprung zur entsprechenden Seite + Box-Hervorhebung im PDF-Render.",
    "RegisterClusterOverlay zeichnet farbige Umrandung um die Cluster-Boxen (gleiche Skalierung wie BoxOverlay).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Register-Cluster im PDF-Render farbig umrandet" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

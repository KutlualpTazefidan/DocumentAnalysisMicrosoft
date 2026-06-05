// Walkthrough recording: upload-pdf
// Tour the PDF-Upload journey: open Dokumente, click „+ PDF hinzufügen“,
// pick a file, observe the success toast, confirm the new row in the table
// with status „Roh“, click „starten“ to land on the Extrahieren page.
//
// The recording uses a temp-renamed copy of the test PDF so the original
// already-extracted slug stays untouched. The temp doc is API-deleted at
// the end so the data root isn't polluted.
//
// Usage:
//   node tests/walkthrough/record/upload-pdf.mjs

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { Recorder } from "../record-walkthrough.mjs";

const SRC_PDF = "/home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft/data/1997_RonKohavi_Standford_Accuracy_Estimation_Model_Selection.pdf";
const DEMO_PDF = "/tmp/Kohavi_Upload_Demo.pdf";
fs.copyFileSync(SRC_PDF, DEMO_PDF);
const DEMO_BASENAME = path.basename(DEMO_PDF);

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

const rec = new Recorder("upload-pdf", BASE);

// ── Step 1: Dokumente-Seite ────────────────────────────────────────────────
await page.goto(`${BASE}/#/admin/inbox`);
await page.waitForSelector("h1", { timeout: 5000 });
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(500);
const rowsBefore = await page.locator("tbody tr").count();
await rec.step(page, "Dokumente-Seite öffnen", {
  actions: ["goto /admin/inbox", "expectVisible h1"],
  notes: [
    `Posteingang-/Dokumente-Liste mit ${rowsBefore} bereits hochgeladenen Dokumenten.`,
    "Topbar zeigt Suchfeld + den „+ PDF hinzufügen“-Button rechts.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: 'button:has-text("PDF hinzufügen")', text: "PDF-Upload-Button — öffnet den nativen Datei-Picker" },
    ],
  }],
});

// ── Step 2: File picker (we set the file directly on the hidden input) ─────
const fileInput = page.locator('input[type=file]');
await fileInput.setInputFiles(DEMO_PDF);
// Wait until the new row shows up in the docs query
await page.waitForFunction((name) =>
  Array.from(document.querySelectorAll("tbody tr td:first-child")).some(td => td.textContent?.includes(name)),
  DEMO_BASENAME, { timeout: 20000 },
).catch(() => {});
await page.waitForTimeout(400);
const rowsAfter = await page.locator("tbody tr").count();
await rec.step(page, `Datei auswählen — „${DEMO_BASENAME}“`, {
  actions: ["pick file via hidden <input type=file>", "wait for new row"],
  notes: [
    "Klick auf den Button öffnet im echten Betrieb den OS-Dateibrowser; im Recording wird die Datei direkt am versteckten <input type=file> gesetzt (gleicher End-Effekt: POST /api/admin/docs mit FormData).",
    `Tabelle wächst um eine Zeile (vorher ${rowsBefore}, jetzt ${rowsAfter}).`,
    "Slug wird aus dem Dateinamen abgeleitet: Kleinbuchstaben, Bindestriche, dedupliziert.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: `tbody tr:has(td:has-text("${DEMO_BASENAME}"))`, text: "Neue Zeile in der Tabelle" },
      { kind: "highlight", selector: ".toast, [role=status]", text: "Erfolgs-Toast „{slug} hochgeladen“" },
    ],
  }],
});

// ── Step 3: New row details ────────────────────────────────────────────────
const newRow = page.locator("tbody tr").filter({ hasText: DEMO_BASENAME });
// Visual cue: outline so it pops in screenshot
await newRow.evaluate(el => el.style.outline = "3px solid #00aff0");
await rec.step(page, "Status der neuen Zeile prüfen — „Roh“, 0 Elemente, Aktion „starten“", {
  actions: [`locate row with "${DEMO_BASENAME}"`],
  notes: [
    "Initialstatus nach Upload ist „Roh“ (DocStatus=raw) — noch keine Boxen, noch keine Extraktion.",
    "Spalten: Dateiname · Seiten · Status · Elemente (=0) · Zuletzt geändert · Aktion („starten“).",
    "„starten“ ist ein Link nach /admin/doc/{slug}/extract.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: `tbody tr:has(td:has-text("${DEMO_BASENAME}")) >> nth=0`, text: "Neue Zeile, Status „Roh“" },
      { kind: "highlight", selector: `tbody tr:has(td:has-text("${DEMO_BASENAME}")) a:has-text("starten")`, text: "„starten“-Link → Extrahieren-Seite" },
    ],
  }],
});

// ── Step 4: Click "starten" → Extract page ─────────────────────────────────
await newRow.locator('a:has-text("starten")').click();
await page.waitForURL(/#\/admin\/doc\/.*\/extract/, { timeout: 8000 });
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(800);
const slug = page.url().split("#")[1].split("/").slice(-2, -1)[0];
await rec.step(page, "Sprung in Extrahieren — Leerzustand vor erster Segmentierung", {
  actions: [`click "starten"`, `URL → /admin/doc/${slug}/extract`],
  notes: [
    "Direkt nach Upload ist die Extrahieren-Seite leer: kein PDF-Render, kein Box-Overlay, kein HTML.",
    "Rechte Seitenleiste zeigt „Seite 1/N“ rot („Nicht extrahiert“) und bietet zwei Eintrittspunkte:",
    "  · „Alle Seiten extrahieren“ (Topbar) — startet das volle MinerU-Pipeline (segmentieren + Text)",
    "  · „Diese Seite extrahieren“ (Seitenleiste) — granularer Lauf für nur eine Seite",
    "Die Sub-Tabs Synthese/Vergleich/Provenienz bleiben grau bis Status „Extrahiert“ erreicht wird.",
  ],
  shots: [{
    annotations: [
      { kind: "highlight", selector: 'button:has-text("Alle Seiten extrahieren")', text: "Auslöser für die volle Extraktion" },
    ],
  }],
});

const outDir = await rec.finish();

// ── Cleanup: drop the demo doc via API so the data root stays clean ────────
try {
  const r = await fetch(`http://127.0.0.1:8001/api/admin/docs/${slug}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": TOKEN },
  });
  console.log("Cleanup DELETE", slug, "→", r.status);
} catch (e) {
  console.log("Cleanup failed:", e.message);
}
fs.rmSync(DEMO_PDF, { force: true });

await browser.close();
console.log("Wrote walkthrough to", outDir);

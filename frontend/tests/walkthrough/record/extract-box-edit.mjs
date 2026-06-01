// Walkthrough recording: extract-box-edit
// Tour modifying an existing box: click on a box in the PDF render, the
// Eigenschaften panel surfaces type-dropdown / Aktiv-Toggle / Diagnose,
// change the type, deactivate it, then revert everything to leave the
// doc as it was found.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

// Snapshot original state of a paragraph box on page 1 so we can restore it.
const segR = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } });
const seg = await segR.json();
const targetBox = seg.boxes.find(b => b.page === 1 && b.kind === "paragraph");
const originalKind = targetBox?.kind;
const originalActive = targetBox?.manually_activated;
const TARGET_ID = targetBox?.box_id;

const rec = new Recorder("extract-box-edit", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);

// Step 1: PDF render with all boxes
await rec.step(page, "PDF-Render mit Box-Overlay — Klick selektiert", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "Jede MinerU-Box ist im PDF-Render als farbiger Rahmen sichtbar (Typ-Farbe aus Legende links).",
    "Klick auf eine Box → Eigenschaften-Panel rechts wird gefüllt.",
    "Verfügbare Edits: Typ-Wechsel (Dropdown), Aktivieren/Deaktivieren, Merge-Up / Merge-Down, Reset, Diagnose.",
    `Test-Box: ${TARGET_ID} (Typ „${originalKind}“ auf Seite 1).`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: TARGET_ID ? `[data-testid="box-${TARGET_ID}"]` : '[data-testid^="box-"]', text: "Box, die wir gleich bearbeiten" },
  ] }],
});

// Step 2: click on the box → Eigenschaften panel populates
if (TARGET_ID) {
  await page.locator(`[data-testid="box-${TARGET_ID}"]`).click({ force: true });
  await page.waitForTimeout(600);
}
await rec.step(page, "Eigenschaften-Panel zeigt Typ + Aktiv-Status", {
  actions: [`click [data-testid="box-${TARGET_ID}"]`],
  notes: [
    "Panel zeigt: Box-ID, Typ-Dropdown, manually-activated-Toggle, Merge-Up / Merge-Down, „Reset to YOLO“.",
    "Außerdem ein Diagnose-Block mit dem Confidence-Score + Caption-Rescue-Events vom letzten Extract-Lauf.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Panel rechts: Eigenschaften der gewählten Box" },
  ] }],
});

// Step 3: Change kind via API (UI uses a Radix dropdown which is brittle to drive)
const newKind = originalKind === "heading" ? "paragraph" : "heading";
if (TARGET_ID) {
  await fetch(`${API}/api/admin/docs/${SLUG}/segments/${TARGET_ID}`, {
    method: "PUT",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ kind: newKind, manually_activated: true }),
  });
  await page.reload();
  await page.waitForLoadState("networkidle").catch(()=>{});
  await page.waitForTimeout(1500);
  await page.locator(`[data-testid="box-${TARGET_ID}"]`).click({ force: true });
  await page.waitForTimeout(400);
}
await rec.step(page, `Typ-Wechsel „${originalKind}“ → „${newKind}“ + aktivieren`, {
  actions: [
    `PUT /segments/${TARGET_ID}  body={kind:"${newKind}", manually_activated:true}`,
    "page.reload() to fetch updated segments",
  ],
  notes: [
    "Der Server akzeptiert Teil-Updates (PUT mit nur den zu ändernden Feldern).",
    "Border-Farbe der Box im PDF-Render wechselt auf die neue Typ-Farbe (siehe Legende links).",
    "Die manually_activated-Flag persistiert, damit ein späterer Re-Extract-Lauf die User-Entscheidung nicht überschreibt.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: TARGET_ID ? `[data-testid="box-${TARGET_ID}"]` : '[data-testid^="box-"]', text: `Box jetzt als „${newKind}“ markiert` },
  ] }],
});

// Cleanup: restore original kind + manually_activated
if (TARGET_ID && originalKind) {
  await fetch(`${API}/api/admin/docs/${SLUG}/segments/${TARGET_ID}`, {
    method: "PUT",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ kind: originalKind, manually_activated: originalActive ?? false }),
  });
  console.log(`Restored box ${TARGET_ID} to kind="${originalKind}", manually_activated=${originalActive}`);
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

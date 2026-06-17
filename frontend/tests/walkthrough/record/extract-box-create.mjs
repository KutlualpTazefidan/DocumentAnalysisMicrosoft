// Walkthrough recording: extract-box-create
// Tour the „neue Box“ flow: click „+ Neue Box“ in the right sidebar, the
// cursor turns crosshair, drag on the PDF render to outline an area, the
// box appears with default type „paragraph“ and is editable in the
// Eigenschaften panel. Temp box is API-deleted at the end so the doc
// stays in its original state.

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
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

const rec = new Recorder("extract-box-create", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);

// Step 1: Right sidebar with „+ Neue Box“ button
await rec.step(page, "Rechte Seitenleiste: „+ Neue Box“", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "Wenn die MinerU-Erkennung eine Box übersieht (z.B. eine Fußnote), legt der Kurator manuell eine neue an.",
    "Eintrittspunkt: „+ Neue Box“-Button im rechten Panel — aktiviert den Crosshair-Modus auf dem PDF-Render.",
    "Im Crosshair-Modus: Mousedown → Drag → Mouseup definiert das Bounding-Box-Rechteck in PDF-Koordinaten.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[aria-label="New box"]', text: "Aktiviert Crosshair / Box-Drawing-Mode" },
  ] }],
});

// Step 2: Create the box via API (UI drag is fragile to automate cleanly)
// Place a box at a clearly unoccupied area near the bottom of page 1.
const PAGE = 1;
const BBOX = [50, 720, 350, 760]; // x1,y1,x2,y2 in PDF coordinates
const r = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, {
  method: "POST",
  headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
  body: JSON.stringify({ page: PAGE, bbox: BBOX, kind: "paragraph" }),
});
const newBox = r.ok ? await r.json() : null;
const newBoxId = newBox?.box_id;
await page.reload();
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(1500);
await rec.step(page, `Neue Box angelegt — bbox ${JSON.stringify(BBOX)} auf Seite ${PAGE}`, {
  actions: [
    "POST /api/admin/docs/{slug}/segments  body={page, bbox, kind:'paragraph'}",
    "page.reload() to fetch fresh segments",
  ],
  notes: [
    "Server vergibt die box_id (sequentiell innerhalb der Seite, Format: p<page>-b<n>).",
    "Default-Kind ist „paragraph“ — kann anschließend per Eigenschaften-Panel-Dropdown geändert werden.",
    "Die Box ist sofort im SegmentsFile + html.html sichtbar (write_segments läuft synchron im POST-Handler).",
    `Neue box_id: ${newBoxId ?? "—"}`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: newBoxId ? `[data-testid="box-${newBoxId}"]` : '[data-testid^="box-"]', text: "Neu angelegte Box auf dem PDF-Render" },
  ] }],
});

// Step 3: Select the new box → Eigenschaften panel + type-dropdown
if (newBoxId) {
  await page.locator(`[data-testid="box-${newBoxId}"]`).click({ force: true });
  await page.waitForTimeout(500);
}
await rec.step(page, "Box-Eigenschaften-Panel zeigt Typ + Aktiv-Toggle", {
  actions: [`click [data-testid="box-${newBoxId}"]`],
  notes: [
    "Auswahl füllt das Eigenschaften-Panel mit der Box-ID, dem Typ-Dropdown (heading/paragraph/table/figure/…), dem Aktiv-Toggle und Diagnose-Infos.",
    "Hier wird der initial vergebene Typ verfeinert — z.B. von „paragraph“ auf „caption“ oder „auxiliary“.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Panel zeigt Eigenschaften für ${newBoxId ?? "die ausgewählte Box"}` },
  ] }],
});

// Cleanup: delete the temp box
if (newBoxId) {
  await fetch(`${API}/api/admin/docs/${SLUG}/segments/${newBoxId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": TOKEN },
  });
  console.log("Temp box", newBoxId, "deleted.");
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

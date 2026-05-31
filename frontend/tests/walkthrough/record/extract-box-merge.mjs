// Walkthrough recording: extract-box-merge
// Tour the merge feature: when MinerU splits one logical paragraph into
// two boxes (or you want to join a paragraph that continues across a
// page break), use „Merge down" / „Merge up" in the Eigenschaften panel.
// We trigger a same-page merge here and unmerge at the end to leave the
// doc state pristine.

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

// Find two adjacent paragraph boxes on the same page
const segR = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } });
const seg = await segR.json();
const sameKindAdjacent = (() => {
  const sorted = [...seg.boxes].sort((a, b) => a.page - b.page || a.reading_order - b.reading_order);
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i], b = sorted[i + 1];
    if (a.page === b.page && a.kind === b.kind && a.kind === "paragraph") return [a, b];
  }
  return null;
})();
const [boxA, boxB] = sameKindAdjacent ?? [null, null];
console.log("Merge candidates:", boxA?.box_id, "+", boxB?.box_id, "on page", boxA?.page);

const rec = new Recorder("extract-box-merge", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);

// Step 1: PDF render with two adjacent boxes
await rec.step(page, "Zwei benachbarte Boxen — Kandidaten für Merge", {
  actions: [`goto /admin/doc/${SLUG}/extract`],
  notes: [
    "MinerU teilt einen logisch zusammenhängenden Absatz manchmal in zwei Boxen — typisch bei Zeilen-Abstand-Sprüngen oder Layout-Artefakten.",
    "Nebeneinander- oder untereinander-stehende Boxen vom gleichen Typ sind Merge-Kandidaten.",
    `Test-Boxen: ${boxA?.box_id} (oben) + ${boxB?.box_id} (darunter) — beide „${boxA?.kind ?? "?"}“ auf Seite ${boxA?.page}.`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: boxA?.box_id ? `[data-testid="box-${boxA.box_id}"]` : '[data-testid^="box-"]', text: "Erste Box (Merge-Anker)" },
    { kind: "highlight", selector: boxB?.box_id ? `[data-testid="box-${boxB.box_id}"]` : '[data-testid^="box-"]', text: "Zweite Box (wird hineingezogen)" },
  ] }],
});

// Step 2: select boxA → panel zeigt Merge-Down-Button
if (boxA?.box_id) {
  await page.locator(`[data-testid="box-${boxA.box_id}"]`).click({ force: true });
  await page.waitForTimeout(500);
}
await rec.step(page, "Box A selektieren → „Merge down“ im Eigenschaften-Panel", {
  actions: [`click [data-testid="box-${boxA?.box_id}"]`],
  notes: [
    "Eigenschaften-Panel zeigt jetzt „Merge down“ / „Merge up“ — abhängig davon, ob es eine nächste/vorherige Box im selben reading_order gibt.",
    "Beim Klick auf „Merge down“ schickt der Frontend POST /segments/{id}/merge-down — der Server zieht die nächste Box rein und vereinigt die bboxes.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Panel-Buttons „Merge up / Merge down“ sichtbar" },
  ] }],
});

// Step 3: trigger merge via API
let merged = null;
if (boxA?.box_id) {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/segments/${boxA.box_id}/merge-down`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN },
  });
  if (r.ok) {
    merged = await r.json();
    await page.reload();
    await page.waitForLoadState("networkidle").catch(()=>{});
    await page.waitForTimeout(1500);
    await page.locator(`[data-testid="box-${boxA.box_id}"]`).click({ force: true }).catch(()=>{});
    await page.waitForTimeout(400);
  } else {
    console.log("merge-down failed:", r.status, await r.text());
  }
}
await rec.step(page, "Nach Merge: eine gemeinsame Box, Text gejoint", {
  actions: [`POST /segments/${boxA?.box_id}/merge-down`, "page.reload() to fetch fresh segments"],
  notes: [
    "Ergebnis: Box A absorbiert Box B — die Quell-Box bleibt mit erweiterter bbox, Box B wird als „continues_to“ markiert.",
    "Im HTML-Editor erscheint der Text als ein zusammenhängendes Element (kein Absatz-Bruch mehr).",
    "Cross-page-Merge funktioniert identisch — die continues_from/continues_to-Indikatoren zeigen den Sprung über Seiten an.",
    "Reversibel via „Unmerge“ am gemergeten Box-Ende oder am Continues-Indikator.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: boxA?.box_id ? `[data-testid="box-${boxA.box_id}"]` : '[data-testid^="box-"]', text: "Gemergte Box (vereint A + B)" },
  ] }],
});

// Cleanup: unmerge to restore state
if (merged && boxA?.box_id) {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/segments/${boxA.box_id}/unmerge-down`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN },
  });
  if (r.ok) {
    console.log("Unmerge restored two separate boxes.");
  } else {
    console.log("Unmerge failed:", r.status, await r.text());
  }
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);

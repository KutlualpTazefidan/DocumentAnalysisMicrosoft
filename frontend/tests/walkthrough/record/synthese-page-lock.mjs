// Walkthrough recording: synthese-page-lock
// Tour the "Diese Seite sperren" toggle in the Synthese tab — locks the
// page against further LLM-Generate runs (prevents accidental overwrite
// of curated Q&A). Uses the same localStorage key as the Extract tab,
// so locking in either view applies everywhere.

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

const rec = new Recorder("synthese-page-lock", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);

// Step 1: Synthese-Seite mit „Diese Seite sperren“-Button
await rec.step(page, "Synthese-Tab: „Diese Seite sperren“ (rechte Seitenleiste)", {
  actions: [`goto /admin/doc/${SLUG}/synthesise`],
  notes: [
    "Sperren markiert die Seite als abgeschlossen — nach LLM-Generate + manueller Kuratierung sollen keine weiteren Auto-Läufe versehentlich gute Q&A überschreiben.",
    "Lock blockiert „Fragen für diese Box generieren“ und „Fragen für die Seite generieren“ — Schutz vor Überschreiben.",
    "Gleicher Lock-State wie im Extrahieren-Tab (gemeinsamer localStorage-Key) — wer dort sperrt, sperrt auch hier.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="synth-page-lock"]', text: "Sperren/Entsperren-Button (unlocked)" },
  ] }],
});

// Step 2: Click → Lock
await page.locator('[data-testid="synth-page-lock"]').click();
await page.waitForTimeout(500);
await rec.step(page, "Seite gesperrt → Button-Label + Stil wechselt", {
  actions: ['click [data-testid="synth-page-lock"]'],
  notes: [
    "Button wechselt: 🔒 „Diese Seite sperren“ → 🔓 „Diese Seite entsperren“ (Blau-Variant).",
    "approvedPages-Set (localStorage) bekommt die aktuelle Page-Nummer dazu.",
    "Generate-Buttons darunter werden disabled — UI-Hinweis verhindert versehentliche Re-Generate-Klicks.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="synth-page-lock"]', text: "Jetzt im Lock-Zustand" },
    { kind: "highlight", selector: 'button:has-text("Fragen für diese Box generieren")', text: "Generate disabled solange gesperrt" },
  ] }],
});

// Step 3: Unlock to leave the state clean
await page.locator('[data-testid="synth-page-lock"]').click();
await page.waitForTimeout(500);
await rec.step(page, "Entsperren → Generate wieder verfügbar", {
  actions: ['click [data-testid="synth-page-lock"]'],
  notes: [
    "Beim Entsperren verschwindet die Seiten-Nummer aus approvedPages → Generate-Buttons werden wieder aktiv.",
    "Status ist nicht server-persistiert (localStorage only) — pro Browser-Profil. Nächste A.x-Iteration soll das server-seitig spiegeln (siehe PageStatus-Sidecar im Extrahieren-Pfad).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Wieder im Default-Zustand (unlocked, Generate aktiv)" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
